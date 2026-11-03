import io

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
        "/": ("observe", 'id="capture-img"'),
        "/search": ("search", 'id="query-form"'),
        "/items": ("items", 'id="objects"'),
        "/timeline": ("timeline", 'id="timeline"'),
    }
    nav_hrefs = ['href="/"', 'href="/search"', 'href="/items"', 'href="/timeline"']

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

    # 四个 URL 返回不同页面，而不是同一页面的隐藏区块。
    bodies = {path: api_client.get(path).text for path in pages}
    assert len({body for body in bodies.values()}) == 4
    assert 'id="capture-img"' not in bodies["/search"]
    assert 'id="query-form"' not in bodies["/"]
    assert 'id="objects"' not in bodies["/timeline"]

    stylesheet = api_client.get("/static/main.css")
    assert stylesheet.status_code == 200
    assert ".app-main" in stylesheet.text

    observe_alias = api_client.get("/observe?capture=1")
    assert observe_alias.status_code == 200
    assert 'data-page="observe"' in observe_alias.text

    workbench = api_client.get("/workbench")
    assert workbench.status_code == 200
    assert "端到端验收工作台" in workbench.text


def test_observe_uses_in_frame_summary_overlay(api_client):
    page = api_client.get("/")
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
    assert 'id="capture-meta"' not in page.text
    assert 'class="observe-side"' not in page.text
    assert 'class="page-subtitle"' not in page.text

    for path in ("/search", "/items", "/timeline"):
        assert 'id="summary-panel"' not in api_client.get(path).text


def test_search_page_is_full_width_without_suggestion_panel(api_client):
    page = api_client.get("/search")
    assert page.status_code == 200
    assert 'class="app-page search-page"' in page.text
    assert 'class="card query-card search-reveal"' in page.text
    assert 'id="query-form"' in page.text
    assert 'id="query-input"' in page.text
    assert 'id="results"' in page.text
    assert "search-reveal" in page.text
    assert 'class="page-subtitle"' not in page.text
    assert 'class="search-side"' not in page.text
    assert "可以这样问" not in page.text
    assert "example-chips" not in page.text

    stylesheet = api_client.get("/static/main.css")
    assert stylesheet.status_code == 200
    assert "findy-search-rise" in stylesheet.text
    assert ".search-page .search-reveal" in stylesheet.text


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
    assert 'id="grid-count"' not in page.text
    assert 'id="back-to-orb"' not in page.text
    assert 'class="items-toolbar-actions"' not in page.text
    assert 'class="page-subtitle"' not in page.text
    assert 'class="page-meta"' not in page.text
    assert "orb-halo" not in page.text
    assert "orb-orbit" not in page.text
    assert "orb-tilt" not in page.text

    stylesheet = api_client.get("/static/main.css")
    assert stylesheet.status_code == 200
    assert ".orb-tile" in stylesheet.text
    assert ".orb-face" in stylesheet.text
    assert ".orb-tile.is-hovered .orb-face" in stylesheet.text
    assert ".object-tile" in stylesheet.text
    assert "touch-action: pan-y pinch-zoom" in stylesheet.text
    assert "findy-items-view-in" in stylesheet.text
    assert "findy-items-tile-in" in stylesheet.text
    assert "findy-orb-spin" not in stylesheet.text
    assert ".orb-halo" not in stylesheet.text
    assert ".orb-orbit" not in stylesheet.text

    script = api_client.get("/static/app.js")
    assert script.status_code == 200
    assert "function createItemsOrb" in script.text
    assert "pointerdown" in script.text
    assert "lostpointercapture" in script.text
    assert "visibilitychange" in script.text
    assert "prefers-reduced-motion" in script.text
    assert "orbCopiesFor" in script.text
    assert "n > 64 ? n" in script.text
    assert "objectsSignature: null" in script.text
    assert "setItemsMode" in script.text


def test_main_pages_share_warm_entrance_motion(api_client):
    for path in ("/", "/items", "/timeline"):
        page = api_client.get(path)
        assert page.status_code == 200
        assert "wm-enter" in page.text

    search = api_client.get("/search")
    assert "search-reveal" in search.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert "@keyframes findy-warm-rise" in theme.text
    assert ".app-main .wm-enter" in theme.text
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
    for path in ("/", "/search", "/items", "/timeline"):
        page = api_client.get(path)
        assert page.status_code == 200
        assert 'name="theme-color" content="#F4F0E8"' in page.text
        assert "/static/warm.css" in page.text
        assert page.text.index("/static/main.css") < page.text.index("/static/warm.css")

    workbench = api_client.get("/workbench")
    assert workbench.status_code == 200
    assert "/static/warm.css" not in workbench.text
    assert "/static/workbench.css" in workbench.text

    theme = api_client.get("/static/warm.css")
    assert theme.status_code == 200
    assert "body.app-main" in theme.text
    for token in ("#f4f0e8", "#e8e1d5", "#d2c6b5", "#756858", "#4c463e", "#a3a77a"):
        assert token in theme.text
    assert ".app-main .orb-tile.is-back .orb-face" in theme.text
    assert ".app-main .toast" in theme.text

    # 工作台继续使用原深色基础变量，不因主界面主题而改变。
    base = api_client.get("/static/styles.css")
    assert base.status_code == 200
    assert "--bg: #070b13" in base.text
    assert "--text: #e8eefc" in base.text
