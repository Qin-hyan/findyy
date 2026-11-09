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
    assert "我的耳机最后出现在哪里？" in page.text
    assert 'class="page-subtitle"' not in page.text
    assert 'class="search-side"' not in page.text
    assert "可以这样问" not in page.text
    assert "example-chips" not in page.text

    script = api_client.get("/static/app.js")
    assert script.status_code == 200
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


def test_home_uses_product_background_and_real_capture_data(api_client):
    page = api_client.get("/")
    assert page.status_code == 200
    assert 'id="home-hero"' in page.text
    assert 'id="home-search-form"' in page.text
    assert 'id="home-capture-img"' in page.text
    assert 'id="home-objects"' in page.text
    assert 'id="home-object-count"' in page.text
    assert 'id="home-source-state"' in page.text
    # 产品图改为 Hero CSS 背景，不再使用独立 img 容器。
    assert 'id="home-product-img"' not in page.text
    assert 'src="/static/images/findy_homepage_camera_original_proportions.png"' not in page.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert 'url("/static/images/findy_homepage_camera_original_proportions.png")' in theme.text
    assert "body.app-main .home-hero" in theme.text
    assert "background-size: cover" in theme.text

    script = api_client.get("/static/app.js")
    assert script.status_code == 200
    for token in ("function loadHome", "renderHomeObjects", "renderHomeCapture", "/api/objects", "/api/captures?limit=1"):
        assert token in script.text
    # 产品图是静态产品摄影，最近观察才是真实抓拍。
    assert "home-capture-img" in script.text
    assert "home-product-img" not in script.text
    # 首页不使用外部图库、AI 生成图或跨站图片。
    assert "findy-tips" not in page.text
    assert not re.search(r'(?:src|href)="https?://', page.text)


def test_product_and_universal_backgrounds_are_local_originals(api_client):
    product = api_client.get("/static/images/findy_homepage_camera_original_proportions.png")
    assert product.status_code == 200
    assert product.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(product.content)) as image:
        assert image.size == (1672, 941)

    universal = api_client.get("/static/images/findy-universal-background.png")
    assert universal.status_code == 200
    assert universal.headers["content-type"].startswith("image/png")
    with Image.open(io.BytesIO(universal.content)) as image:
        assert image.size == (1672, 941)

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert 'url("/static/images/findy_homepage_camera_original_proportions.png")' in theme.text
    assert 'url("/static/images/findy-universal-background.png")' in theme.text
    assert "body.app-main:not(.home-page)" in theme.text
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
        "evidence_image_url",
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
        assert 'name="theme-color" content="#F6F3EC"' in page.text
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
