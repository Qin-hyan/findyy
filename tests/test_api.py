import io
import re

from PIL import Image


def test_status_endpoint(api_client):
    r = api_client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["source"]["type"] == "replay"
    assert data["config"]["detector"] == "mock"
    assert isinstance(data["classes"], list) and data["classes"]


def test_capture_replay_and_image(api_client):
    r = api_client.post("/api/capture")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["capture_id"] == 1
    assert len(data["detections"]) == 2
    assert data["capture"]["time_synced"] is True

    img = api_client.get(f"/api/captures/{data['capture_id']}/image")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"
    assert img.content.startswith(b"\xff\xd8")

    thumb = api_client.get(f"/api/captures/{data['capture_id']}/image?thumb=1")
    assert thumb.status_code == 200

    det = data["detections"][0]
    crop = api_client.get(det["crop_url"])
    assert crop.status_code == 200


def test_captures_list_and_detail(api_client):
    api_client.post("/api/capture")
    r = api_client.get("/api/captures?limit=5")
    assert r.status_code == 200
    assert len(r.json()["captures"]) == 1
    detail = api_client.get("/api/captures/1")
    assert detail.status_code == 200
    assert len(detail.json()["detections"]) == 2
    assert api_client.get("/api/captures/999").status_code == 404


def test_query_endpoint(api_client):
    api_client.post("/api/capture")
    r = api_client.post("/api/query", json={"text": "杯子在哪？"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "found"
    assert "桌面左侧" in data["answer"]
    assert data["parsed"]["class_zh"] == "杯子"

    empty = api_client.post("/api/query", json={"text": ""})
    assert empty.status_code == 422


def test_objects_and_track_endpoints(api_client):
    api_client.post("/api/capture")
    objects = api_client.get("/api/objects")
    assert objects.status_code == 200
    items = objects.json()["objects"]
    assert len(items) == 2
    track_id = items[0]["track_id"]
    detail = api_client.get(f"/api/tracks/{track_id}")
    assert detail.status_code == 200
    label = api_client.post(f"/api/tracks/{track_id}/label", json={"label": "我的杯子"})
    assert label.status_code == 200
    assert api_client.get(f"/api/tracks/{track_id}").json()["track"]["label"] == "我的杯子"


def test_upload_observe_endpoint(api_client):
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 40, 40)).save(buf, format="JPEG")
    r = api_client.post(
        "/api/observe",
        files={"file": ("frame.jpg", buf.getvalue(), "image/jpeg")},
        data={"captured_at_utc": "2026-10-28T03:00:00Z"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    # 上传未提供本地时间，但 UTC 时间已给出
    assert data["capture"]["time_synced"] is True

    bad = api_client.post(
        "/api/observe",
        files={"file": ("bad.jpg", b"not-a-jpeg", "image/jpeg")},
    )
    assert bad.status_code == 400


def test_service_start_stop(api_client):
    start = api_client.post("/api/service/start")
    assert start.status_code == 200 and start.json()["ok"] is True
    stop = api_client.post("/api/service/stop")
    assert stop.status_code == 200 and stop.json()["ok"] is True


def test_health_and_index(api_client):
    health = api_client.get("/api/health")
    assert health.status_code == 200 and health.json()["db"] is True
    index = api_client.get("/")
    assert index.status_code == 200
    assert "Findy" in index.text


def test_main_pages_are_distinct_navigation_targets(api_client):
    pages = {
        "/": ("home", 'id="home-hero"'),
        "/observe": ("observe", 'id="capture-img"'),
        "/search": ("search", 'id="query-form"'),
        "/items": ("items", 'id="objects"'),
        "/timeline": ("timeline", 'id="timeline"'),
    }
    nav_hrefs = ['href="/"', 'href="/observe"', 'href="/search"', 'href="/items"', 'href="/timeline"']

    for path, (page, marker) in pages.items():
        response = api_client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert f'data-page="{page}"' in response.text
        assert marker in response.text
        assert 'href="/workbench"' in response.text
        assert 'id="header-device"' not in response.text
        assert "本机在线" not in response.text
        assert 'class="device-chip"' not in response.text
        assert "/static/main.css" in response.text
        for href in nav_hrefs:
            assert href in response.text

    # 五个 URL 返回不同页面，而不是同一页面的隐藏区块。
    bodies = {path: api_client.get(path).text for path in pages}
    assert len({body for body in bodies.values()}) == 5
    assert 'id="home-hero"' not in bodies["/observe"]
    assert 'id="capture-img"' not in bodies["/search"]
    assert 'id="query-form"' not in bodies["/"]
    assert 'id="objects"' not in bodies["/timeline"]

    stylesheet = api_client.get("/static/main.css")
    assert stylesheet.status_code == 200
    assert ".app-main" in stylesheet.text

    script = api_client.get("/static/app.js")
    assert "header-device" not in script.text
    assert "本机在线" not in script.text
    assert "本机离线" not in script.text

    observe_alias = api_client.get("/observe?capture=1")
    assert observe_alias.status_code == 200
    assert 'data-page="observe"' in observe_alias.text
    assert 'id="capture-img"' in observe_alias.text

    workbench = api_client.get("/workbench")
    assert workbench.status_code == 200
    assert "端到端验收工作台" in workbench.text


def test_observe_uses_in_frame_summary_overlay(api_client):
    page = api_client.get("/observe")
    assert page.status_code == 200
    assert 'class="capture-stage"' in page.text
    assert 'id="summary-panel"' in page.text
    assert 'id="summary-trigger"' in page.text
    assert 'aria-expanded="false"' in page.text
    assert 'id="summary-hotzone"' in page.text
    assert 'id="stage-detections"' in page.text
    assert 'id="capture-source"' in page.text
    assert 'id="capture-btn"' in page.text
    assert 'id="auto-btn"' in page.text
    assert 'id="observe-detail-btn"' in page.text
    assert 'id="observe-recent"' in page.text
    assert 'id="capture-meta"' not in page.text

    for path in ("/", "/search", "/items", "/timeline"):
        assert 'id="summary-panel"' not in api_client.get(path).text


def test_search_page_has_workspace_filters_and_results(api_client):
    page = api_client.get("/search")
    assert page.status_code == 200
    assert 'class="app-page search-page"' in page.text
    assert 'class="search-bar wm-enter"' in page.text
    assert 'id="query-form"' in page.text
    assert 'id="query-input"' in page.text
    assert 'id="results"' in page.text
    assert 'id="filter-categories"' in page.text
    assert 'id="filter-ranges"' in page.text
    assert "data-filter-category" in page.text
    assert "data-filter-range" in page.text
    assert "我的耳机在哪" in page.text
    assert 'class="page-subtitle"' not in page.text
    assert 'class="search-side"' not in page.text
    assert "可以这样问" not in page.text
    assert "example-chips" not in page.text
    assert "最近一次本机观察" not in page.text
    assert "search-hero-art" not in page.text
    assert "search-hero-img" not in page.text

    script = api_client.get("/static/app.js")
    assert script.status_code == 200
    assert "search-hero-img" not in script.text
    assert "search-hero-art" not in script.text
    for token in (
        "loadSearchBase",
        "renderFilterCategories",
        "searchRangeMatches",
        "renderSearchItems",
        "/api/objects",
    ):
        assert token in script.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert ".filter-panel" in theme.text
    assert ".result" in theme.text
    assert ".search-hero-art" not in theme.text


def test_items_page_has_orb_gallery_and_mode_switch(api_client):
    page = api_client.get("/items")
    assert page.status_code == 200
    assert 'id="items-page"' in page.text
    assert 'id="orb-stage"' in page.text
    assert 'role="group"' in page.text
    assert 'aria-roledescription="可拖动物品球"' in page.text
    assert 'id="orb-sphere"' in page.text
    assert 'id="orb-count"' in page.text
    assert 'id="objects-count"' in page.text
    assert 'id="orb-hint"' in page.text
    assert 'id="orb-selection"' in page.text
    assert 'data-items-mode="orb"' in page.text
    assert 'data-items-mode="grid"' in page.text
    assert 'id="grid-view"' in page.text
    assert 'id="objects"' in page.text
    assert 'id="grid-count"' in page.text
    assert 'id="item-dialog"' in page.text
    assert 'id="back-to-orb"' not in page.text
    assert 'class="items-toolbar-actions"' not in page.text
    assert 'class="page-meta"' not in page.text
    assert "orb-halo" not in page.text
    assert "orb-orbit" not in page.text
    assert "orb-tilt" not in page.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    for token in (
        ".orb-tile",
        ".orb-face",
        ".orb-tile.is-hovered .orb-face",
        ".object-tile",
        "touch-action: pan-y pinch-zoom",
        "findy-items-view-in",
        "findy-items-tile-in",
        ".item-dialog",
    ):
        assert token in theme.text
    assert "findy-orb-spin" not in theme.text
    assert ".orb-halo" not in theme.text
    assert ".orb-orbit" not in theme.text

    script = api_client.get("/static/app.js")
    assert script.status_code == 200
    for token in (
        "function createItemsOrb",
        "pointerdown",
        "lostpointercapture",
        "visibilitychange",
        "prefers-reduced-motion",
        "orbCopiesFor",
        "n > 64 ? n",
        "objectsSignature: null",
        "setItemsMode",
        "function openItemDetail",
        "/api/tracks/${trackId}",
    ):
        assert token in script.text


def test_home_has_carousel_without_content_sections(api_client):
    page = api_client.get("/")
    assert page.status_code == 200
    assert 'id="home-hero"' in page.text
    assert 'id="home-search-form"' in page.text
    assert "Findy，" in page.text
    assert "记住你的物品" in page.text
    assert "自然界的Ctrl+F" in page.text
    assert page.text.count("data-hero-slide") == 2
    assert page.text.count("data-hero-dot") == 2
    # 首页只保留 Hero 轮播与搜索，不恢复数据内容区。
    assert "home-sections" not in page.text
    assert "home-overview" not in page.text
    assert 'id="home-object-count"' not in page.text
    assert 'id="home-capture-count"' not in page.text
    assert 'id="home-device-state"' not in page.text
    assert 'id="home-capture-img"' not in page.text
    assert 'id="home-objects"' not in page.text
    assert 'id="home-capture"' not in page.text
    assert "本机概览" not in page.text
    assert "最近记住的物品" not in page.text
    # 产品图作为 Hero CSS 背景，不使用独立 img 容器。
    assert 'id="home-product-img"' not in page.text
    assert 'src="/static/images/findy_homepage_camera_original_proportions.png"' not in page.text
    assert 'src="/static/images/findy_homepage_ecosystem_scene.png"' not in page.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert 'url("/static/images/findy_homepage_camera_original_proportions.png")' in theme.text
    assert 'url("/static/images/findy_homepage_ecosystem_scene.png")' in theme.text
    assert "body.app-main .hero-slide" in theme.text
    assert "transition: opacity 0.8s ease" in theme.text
    assert "background-size: cover" in theme.text

    script = api_client.get("/static/app.js")
    assert script.status_code == 200
    for token in ("async function loadHome", "initHeroCarousel", "setInterval", "6000"):
        assert token in script.text
    assert "renderHomeObjects" not in script.text
    assert "renderHomeCapture" not in script.text
    # 首页不使用外部图库、AI 生成图或跨站图片。
    assert "findy-tips" not in page.text
    assert not re.search(r'(?:src|href)="https?://', page.text)


def test_main_ui_copy_has_no_chinese_full_stop(api_client):
    for path in ("/", "/observe", "/search", "/items", "/timeline"):
        page = api_client.get(path)
        assert page.status_code == 200
        assert "\u3002" not in page.text
    script = api_client.get("/static/app.js")
    assert script.status_code == 200
    assert "\u3002" not in script.text
    assert "stripPeriods" in script.text


def test_product_and_universal_backgrounds_are_local_originals(api_client):
    product = api_client.get("/static/images/findy_homepage_camera_original_proportions.png")
    assert product.status_code == 200
    assert product.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(product.content)) as image:
        assert image.size == (1672, 941)

    ecosystem = api_client.get("/static/images/findy_homepage_ecosystem_scene.png")
    assert ecosystem.status_code == 200
    assert ecosystem.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(ecosystem.content)) as image:
        assert image.size == (1672, 941)

    universal = api_client.get("/static/images/findy-universal-background.png")
    assert universal.status_code == 200
    assert universal.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(universal.content)) as image:
        assert image.size == (1672, 941)

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert 'url("/static/images/findy_homepage_camera_original_proportions.png")' in theme.text
    assert 'url("/static/images/findy_homepage_ecosystem_scene.png")' in theme.text
    assert 'url("/static/images/findy-universal-background.png")' in theme.text
    assert "body.app-main:not(.home-page)" in theme.text
    assert "--home-header-height" in theme.text
    assert "padding: var(--home-header-height) 0 0" in theme.text
    assert "grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr)" in theme.text
    assert "background-size: cover" in theme.text
    assert "background-repeat: no-repeat" in theme.text
    assert "#f6f3ec" in theme.text

    # 产品图只作为首页 Hero 背景；通用背景图只通过 warm.css 应用到其他页面。
    home = api_client.get("/").text
    assert "/static/images/findy_homepage_camera_original_proportions.png" not in home
    assert "/static/images/findy-universal-background.png" not in home
    for path in ("/observe", "/search", "/items", "/timeline"):
        page = api_client.get(path).text
        assert "/static/images/findy_homepage_camera_original_proportions.png" not in page
        assert "/static/images/findy-universal-background.png" not in page
        assert "/static/warm.css" in page


def test_search_and_items_expose_real_data_contracts(api_client):
    script = api_client.get("/static/app.js")
    assert script.status_code == 200
    for token in (
        "evidence_crop_url",
        "openItemDetail",
        "objectSearchHref",
        "localDateLabel",
        "sourceName",
    ):
        assert token in script.text
    assert "https://" not in script.text
    assert "http://" not in script.text


def test_main_pages_share_warm_entrance_motion(api_client):
    for path in ("/", "/observe", "/search", "/items", "/timeline"):
        page = api_client.get(path)
        assert page.status_code == 200
        assert "wm-enter" in page.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert "@keyframes findy-warm-rise" in theme.text
    assert ".wm-enter" in theme.text
    assert "animation-delay: var(--enter-delay, 0ms)" in theme.text
    assert "prefers-reduced-motion: reduce" in theme.text
    assert ".object-tile.is-entering" in theme.text

    main = api_client.get("/static/main.css")
    assert ".app-main .object-tile.is-entering" in main.text
    assert ".app-main .object-tile {" in main.text


def test_timeline_is_grouped_expandable_activity_feed(api_client):
    page = api_client.get("/timeline")
    assert page.status_code == 200
    assert 'class="timeline-board"' in page.text
    assert 'class="page-subtitle"' not in page.text
    assert 'class="card"' not in page.text
    assert "timeline-card" not in page.text
    assert 'id="timeline"' in page.text
    assert 'id="timeline-end"' in page.text

    script = api_client.get("/static/app.js")
    assert script.status_code == 200
    for token in (
        "timelineDayKey",
        "timelineDayMeta",
        "timeline-event-card",
        "timeline-detail-inner",
        "timeline-detail-link",
        "aria-expanded",
        "timelineEntered",
        "timelineSignature",
        "if (signature === state.timelineSignature) return;",
    ):
        assert token in script.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    for token in (
        ".timeline-day-head",
        ".timeline-events::before",
        ".timeline-event-card",
        ".timeline-event.is-latest .timeline-event-card",
        ".timeline-event.is-latest .timeline-thumb-wrap",
        ".timeline-detail-inner",
        ".timeline-evidence-box",
        "@keyframes findy-timeline-detail-in",
        ".timeline-event.is-latest .timeline-node",
    ):
        assert token in theme.text


def test_warm_minimal_theme_is_isolated_from_workbench(api_client):
    for path in ("/", "/observe", "/search", "/items", "/timeline"):
        page = api_client.get(path)
        assert page.status_code == 200
        assert 'name="theme-color" content="#111111"' in page.text
        assert "/static/warm.css" in page.text
        assert page.text.index("/static/main.css") < page.text.index("/static/warm.css")

    workbench = api_client.get("/workbench")
    assert workbench.status_code == 200
    assert "/static/warm.css" not in workbench.text
    assert "/static/workbench.css" in workbench.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert "body.app-main" in theme.text
    for token in ("#f6f3ec", "#fbfaf7", "#e4ded2", "#aeb98d", "#1d1b17"):
        assert token in theme.text
    assert ".app-main .orb-tile.is-back .orb-face" in theme.text
    assert ".app-main .toast" in theme.text

    # 工作台继续使用原深色基础变量，不因主界面主题而改变。
    base = api_client.get("/static/styles.css")
    assert base.status_code == 200
    assert "--bg: #070b13" in base.text
    assert "--text: #e8eefc" in base.text


def test_brand_assets_and_manifest_are_served(api_client):
    favicon = api_client.get("/brand/favicon.ico")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/")
    assert len(favicon.content) > 1000
    with Image.open(io.BytesIO(favicon.content)) as image:
        assert {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)} <= image.info["sizes"]

    home = api_client.get("/").text
    versioned_favicon = re.search(r'href="(/brand/favicon\.ico\?v=[^"]+)"', home)
    assert versioned_favicon is not None
    served_version = api_client.get(versioned_favicon.group(1))
    assert served_version.status_code == 200
    assert served_version.content == favicon.content

    lockup = api_client.get("/brand/svg/logo-lockup.svg")
    assert lockup.status_code == 200
    assert lockup.headers["content-type"].startswith("image/svg+xml")
    assert 'viewBox="0 0 159.1 52.0"' in lockup.text
    assert 'fill="currentColor"' in lockup.text

    inverse = api_client.get("/brand/svg/logo-lockup-inverse.svg")
    assert inverse.status_code == 200
    assert 'fill="#ffffff"' in inverse.text

    icon = api_client.get("/brand/png/app-icon/findy-app-192.png")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(icon.content)) as image:
        assert image.size == (192, 192)

    og_image = api_client.get("/brand/og-image-1200x630.png")
    assert og_image.status_code == 200
    with Image.open(io.BytesIO(og_image.content)) as image:
        assert image.size == (1200, 630)

    manifest = api_client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert "no-store" in manifest.headers.get("cache-control", "")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    data = manifest.json()
    assert data["name"] == "Findy"
    assert data["start_url"] == "/"
    assert data["display"] == "standalone"
    assert data["theme_color"] == "#111111"
    assert {item["sizes"] for item in data["icons"]} == {"192x192", "256x256", "512x512"}
    for item in data["icons"]:
        response = api_client.get(item["src"])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/png")


def test_pages_use_brand_head_references_and_nav_lockups(api_client):
    app_pages = ("/", "/observe", "/search", "/items", "/timeline")
    for path in app_pages:
        page = api_client.get(path)
        assert page.status_code == 200
        assert "no-store" in page.headers.get("cache-control", "")
        assert '<link rel="icon" href="/brand/favicon.ico?v=' in page.text
        assert 'sizes="any" />' in page.text
        assert (
            '<link rel="icon" type="image/png" sizes="32x32" '
            'href="/brand/png/app-icon/findy-app-32.png?v='
        ) in page.text
        assert (
            '<link rel="apple-touch-icon" sizes="192x192" '
            'href="/brand/png/app-icon/findy-app-192.png?v='
        ) in page.text
        assert '<link rel="manifest" href="/manifest.webmanifest" />' in page.text
        assert '<meta property="og:image" content="/brand/og-image-1200x630.png" />' in page.text
        assert (
            '<img class="app-brand-logo" src="/brand/svg/logo-lockup.svg" '
            'alt="Findy" width="110" height="36" />'
        ) in page.text
        assert 'class="logo app-logo"' not in page.text
        assert "app-brand-copy" not in page.text

    workbench = api_client.get("/workbench")
    assert workbench.status_code == 200
    assert "no-store" in workbench.headers.get("cache-control", "")
    assert '<link rel="manifest" href="/manifest.webmanifest" />' in workbench.text
    assert '<link rel="icon" href="/brand/favicon.ico?v=' in workbench.text
    assert (
        '<img class="brand-logo" src="/brand/svg/logo-lockup-inverse.svg" '
        'alt="Findy" width="110" height="36" />'
    ) in workbench.text
    assert "filter:" not in workbench.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert "body.app-main .app-brand-logo" in theme.text
    assert "height: 36px" in theme.text

    workbench_theme = api_client.get("/static/workbench.css")
    assert workbench_theme.status_code == 200
    assert ".workbench .brand-logo" in workbench_theme.text
    assert "height: 36px" in workbench_theme.text
