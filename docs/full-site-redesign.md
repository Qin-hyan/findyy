# Findy 全站 UI 视觉改版

分支：`feature/full-site-ui-redesign`
基线：`main` @ `0cc7744`（本地 `main` 比 `origin/main` 领先 10 个提交）
本轮不 push、不 merge、不重启生产服务。

## 1. 五张参考图的设计语言

五张参考图共同指向一套“温暖、克制、以物品照片为主角”的界面：

- **底色**：奶油白大底，卡片比页面略亮，不使用纯白满屏。
- **文字**：近黑深咖作为主文字，灰棕承担说明文字；标题字重高、字距紧。
- **强调色**：低饱和鼠尾草绿，只用于当前导航、状态点、筛选选中、最新节点。
- **层级**：大标题 + 充足留白；信息通过卡片、细分隔线和字号建立层级，而不是靠高饱和色块。
- **形态**：大圆角、极轻暖色阴影、1px 暖灰边框；图片本身承担主要视觉重量。
- **导航**：桌面为悬浮白色胶囊；首页为更轻的透明顶栏。移动端折成两行横向滚动。
- **内容页**：搜索页是“筛选侧栏 + 结果列表”，物品页是“球体 + 物品网格”，时间线是“日期分组 + 左侧细轨 + 事件行”。

实现中没有照搬参考图的商品/场景照片，也没有使用外部图库；所有物品图和抓拍图都来自本项目真实采集记录。

## 2. 最终视觉规范

| 用途 | 色值 |
|---|---|
| 页面背景奶油白 | `#F6F3EC` |
| 页面暖灰底 | `#F0ECE3` |
| 卡片表面 | `#FBFAF7` |
| 强表面/输入框 | `#FFFFFF` |
| 软表面 | `#F2EEE6` |
| 常规边框 | `#E4DED2` |
| 强边框 | `#D6CDBD` |
| 主文字 | `#1D1B17` |
| 次级文字 | `#35312B` |
| 说明文字 | `#706A61` |
| 弱说明文字 | `#8D8579` |
| 鼠尾草绿 | `#AEB98D` |
| 深鼠尾草绿 | `#6F7752` |
| 浅绿选中底 | `#EDF0E2` |
| 浅绿悬停底 | `#F4F6ED` |
| 成功 | `#4F6239` |
| 警告 | `#8A5A24` |
| 失败 | `#93483D` |

- 字体：`Segoe UI Variable / Segoe UI / PingFang SC / Hiragino Sans GB / Microsoft YaHei`。
- 字距：大标题 `-0.05em` 到 `-0.065em`；正文正常。
- 圆角：页面大卡 28px，普通卡 20px，行卡 18px，缩略图 15–17px，胶囊 999px。
- 阴影：`0 10px 30px rgba(57,49,37,.06)` 至 `0 30px 80px rgba(57,49,37,.13)`，不使用冷色/霓虹阴影。
- 动效：统一 `findy-warm-rise`，`0.42s`，`cubic-bezier(.22,.75,.2,1)`，位移 14px；`prefers-reduced-motion` 全部关闭。

### 品牌资源与图标
- 品牌素材完整复制到 `web/public/brand/`，包含 6 个 SVG、20 个 PNG、`favicon.ico`、`og-image-1200x630.png` 与 `logo-usage.md`。
- FastAPI 挂载 `/brand` 静态目录，并提供 `/manifest.webmanifest`；manifest 位于 `web/public/manifest.webmanifest`。
- 所有页面统一引用 `/brand/favicon.ico`、32px app icon、192px apple-touch-icon、manifest 与 `og:image`。
- 五个主页面导航使用 `/brand/svg/logo-lockup.svg`，显示高度 36px、宽度 110px，保持 159.1:52 原始比例。
- 深色工作台顶栏使用 `/brand/svg/logo-lockup-inverse.svg`，不使用 CSS 滤镜、不拉伸、不改比例。
- favicon 为 16/24/32/48/64 多尺寸松鼠图标；manifest 引用 192/256/512 三个 App 图标。
- 所有页面的 favicon 与 apple-touch-icon 引用带 `?v=c360e51c8471` 版本参数，强制浏览器重新拉取图标，避免标签页继续显示旧 “F” 图标。
- 页面 HTML 与 manifest 响应使用 `no-cache, no-store, must-revalidate`，避免在多个页面之间切换时继续显示旧导航或旧 favicon。

## 3. 页面改造

### 首页 `/`
- 首页 Hero 使用两张产品摄影背景轮播，间隔 6 秒、800ms 淡入淡出；两个圆点可手动切换。
- 鼠标悬停暂停轮播，标题、副标题和搜索框始终固定。
- 标题为 `Findy，记住你的物品`，副标题为 `自然界的Ctrl+F`。
- 标题行高 1.18、字重 600、字距放松；桌面 Hero 从导航栏底部无缝开始，填满首屏剩余高度。
- 首页导航栏底部与 Hero 背景图顶部直接相接，不再保留奶油色空白带。
- 顶部导航整体相对整条栏居中，logo 保持左侧原位，右侧只保留用户头像。
- 首页只保留 Hero 轮播、标题和搜索，不展示本机概览、最近观察或最近物品。
- 全站移除英文眉题；功能说明只保留必要操作提示。
- 所有主页面与工作台文案不再使用中文句号。

### 首页产品摄影与统一背景
- 首页 Hero 使用 `web/static/images/findy_homepage_camera_original_proportions.png` 和 `web/static/images/findy_homepage_ecosystem_scene.png` 两张原图作为 CSS 背景，不使用独立 `<img>` 卡片。
- 单品图 `background-size: cover`；生态图桌面 `120% auto`、窄屏 `140% auto` 或 `cover`，只做等比缩放与裁切，不拉伸、不压扁。
- 左侧叠加米白渐变保证文字可读；桌面与移动端分别设置背景定位。
- 移动端切换为上下结构，背景优先保证摄像头主体完整可见。
- 其他四个主页面统一使用 `web/static/images/findy-universal-background.png`（同为 `1672×941`），通过 `body.app-main:not(.home-page)` 的 `background` 应用一次，不在每个页面复制图片。
- 通用背景使用 `cover`、`no-repeat`、`fixed`，叠加 84%–94% 暖白遮罩；保持宽高比例，低视觉权重，不干扰物品照片与文字。
- 首页与通用背景严格区分：首页不加载通用背景，其他页面不加载产品图。

### 最近观察 `/observe`
- 保留原抓拍、自动采集、识别摘要、检测框叠加能力。
- 大图 + 右侧摘要卡；点击“查看识别详情”打开原有识别摘要。
- 下方按日期分组展示最近 6 条真实抓拍；点击行切换当前观察。
- 仍支持 `/observe?capture={id}`。

### 找找物品 `/search`
- 顶部自然语言搜索；原右上角“最近一次本机观察”模块已删除，搜索区改为单列布局。
- 左侧真实分类计数（由 `/api/objects` 与当前查询结果计算）。
- 支持物品类型、最近一周/最近一个月筛选；筛选只作用于本地已返回结果。
- 结果卡展示真实裁剪图、时间、区域、来源、关联状态和“查看详情”。
- 保留 `/search?q=...&autorun=1` 深链。
- 无结果、无图片、接口失败均有明确状态。

### 我的物品 `/items`
- 左侧模式切换，默认同时展示 3D 球体与“全部物品”网格；平铺模式只保留网格。
- 物品网格使用每件物品真实 `evidence_crop_url`，5/4/3/2 列响应式。
- 新增物品详情弹层，用真实 `/api/tracks/{track_id}` 数据展示观测次数、最近出现、来源、最近观测记录。
- 球体继续支持拖拽、惯性、方向键、减少动态效果与键盘焦点。

### 观察时间线 `/timeline`
- 按日期分组的纵向 Activity Timeline，最新日期/记录置顶。
- 左侧细轨 + 事件节点；最新节点使用鼠尾草绿。
- 最新一条记录整体略放大：缩略图、卡片高度、时间字号略大于历史记录，形成视觉落点。
- 每行：真实缩略图、准确时间、`来自 · ESP32`、识别物品、区域/识别数量、展开箭头。
- 点击展开真实原图、检测框、识别证据和关联分；保留“打开完整观察”入口。
- 时间线使用内容签名，轮询不重建 DOM、不重播动画；加载结束有明确状态。

## 4. 真实图片与数据来源

- 首页轮播背景：`/static/images/findy_homepage_camera_original_proportions.png`、`/static/images/findy_homepage_ecosystem_scene.png`，均为静态产品摄影。
- 其他页面统一背景：`/static/images/findy-universal-background.png`，原始无摄像头背景。
- 首页最近观察、最近观察页、时间线：`/api/captures/{id}/image` 或 `?thumb=1`。
- 物品网格、球体、搜索结果：`/api/detections/{detection_id}/crop`。
- 物品详情：`/api/tracks/{track_id}` 返回的检测裁剪图。
- 所有图片均在本机 SQLite 与本地文件中；没有外链图片、没有 AI 生成图、没有图库图片。
- 对每件有图的物品，验收脚本核对其裁剪图确实属于该 `track_id` 的检测记录。
- 图片缺失/加载失败时显示“暂无图片/图片不可用/无图”，不伪造图片。

## 5. 验证

```powershell
.\.venv314\Scripts\python.exe -m pytest -q
node --check web\static\app.js
D:\Anaconda3\python.exe .tmp\acceptance_fullsite.py
D:\Anaconda3\python.exe .tmp\acceptance_brand.py
```

- 自动化测试：**105 passed**
- 浏览器验收：全站 **149 项**、品牌专项 **56 项**，全部通过
- 覆盖：五个页面的真实数据、首页双背景轮播 / 6 秒切换 / 800ms 淡入淡出 / 圆点切换 / 悬停暂停、标题排版、首页 Hero 与导航无缝衔接、导航居中、搜索页移除“最近一次观察”、顶栏移除“本机在线”、时间线最新记录放大、首页不显示内容区、全站无句号与英文眉题、搜索筛选与空状态、物品详情弹层、时间线展开与防重播、桌面/平板/手机横向溢出、减少动态效果、工作台隔离、抓拍数量与轨迹数量不变。
- 品牌专项覆盖：favicon / manifest / og:image 路径、品牌文件完整复制、正片与反白 logo 使用场景、36px 显示尺寸、159.1:52 比例、SVG 1x/2x 清晰度、无滤镜、无横向溢出、无 404。
- 验收期间未触发 `/api/capture`、`/api/observe`、`/api/service/*`、`/api/acceptance/*`。

截图目录：`docs/evidence/full-site-redesign/`。
验证明细：`docs/evidence/full-site-redesign/verification.json`。
品牌验证明细：`docs/evidence/full-site-redesign/brand_verification.json`。

## 6. 已知限制

- 当前真实数据只覆盖桌面物品（键盘、鼠标、笔记本电脑、手机、充电器），因此页面不会出现参考图中的耳机、背包等类别。
- 部分旧检测裁剪图文件缺失，界面会显示“无图”占位，而不是补造图片。
- 真实手机/平板触控、Firefox、Safari、完整读屏流程未验证。
- 未运行真实设备抓拍/回放，也未对生产 `8766` 实例做验收。