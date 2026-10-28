from findy.query import detect_intent, parse_query, resolve_time_window


def test_parse_last_seen(catalog, regions):
    plan = parse_query("我的钥匙最后出现在哪里？", catalog, regions)
    assert plan.intent == "last_seen"
    assert plan.class_zh == "钥匙"


def test_parse_color_attribute(catalog, regions):
    plan = parse_query("红色杯子在哪？", catalog, regions)
    assert plan.intent == "last_seen"
    assert plan.class_zh == "杯子"
    assert plan.color == "红色"


def test_parse_history(catalog, regions):
    plan = parse_query("手机是什么时候最后一次看到的？", catalog, regions)
    assert plan.intent == "history"
    assert plan.class_zh == "手机"


def test_parse_moved_with_today_window(catalog, regions):
    plan = parse_query("今天鼠标动过吗？", catalog, regions)
    assert plan.intent == "moved"
    assert plan.class_zh == "鼠标"
    assert plan.time_window == "today"
    assert plan.time_start_utc and plan.time_end_utc


def test_parse_list_does_not_match_context_class(catalog, regions):
    plan = parse_query("桌上都有哪些东西？", catalog, regions)
    assert plan.intent == "list"
    assert plan.class_zh is None  # 「书桌」是 context_only，不应被当成要查的物品


def test_parse_count_and_presence(catalog, regions):
    assert parse_query("键盘有几个？", catalog, regions).intent == "count"
    presence = parse_query("我的电脑还在吗？", catalog, regions)
    assert presence.intent == "presence"
    assert presence.class_zh == "笔记本电脑"


def test_parse_help_without_entity(catalog, regions):
    plan = parse_query("你好", catalog, regions)
    assert plan.intent == "help"


def test_parse_region_filter(catalog, regions):
    plan = parse_query("桌面右侧有什么？", catalog, regions)
    assert plan.intent == "list"
    assert plan.region == "桌面右侧"


def test_detect_intent_priority():
    assert detect_intent("钥匙在哪") == "last_seen"
    assert detect_intent("钥匙移动过吗") == "moved"
    assert detect_intent("钥匙什么时候出现的") == "history"
    assert detect_intent("你能做什么") == "help"


def test_time_window_yesterday():
    name, start, end = resolve_time_window("昨天鼠标动过吗", "Asia/Shanghai")
    assert name == "yesterday" and start < end
    assert start.endswith("Z") and end.endswith("Z")


def test_time_window_none_for_neutral_query():
    name, start, end = resolve_time_window("钥匙在哪", "Asia/Shanghai")
    assert name is None and start is None and end is None


def test_parse_empty_query_is_help(catalog, regions):
    plan = parse_query("   ", catalog, regions)
    assert plan.intent == "help"
    assert plan.notes