# Findy Logo 使用规范

**版本** v1.1 ｜ **形态** 松鼠吉祥物 + 「Findy」字标 ｜ **色彩** 纯黑白

## 一、设计逻辑

松鼠的散贮（scatter-hoarding）本能：把食物分散埋藏在数十至数千个位置，数周后仍能凭空间记忆逐一找回。这正是 Findy 的完整闭环——**观察（摄像头持续看）→ 记忆（记录位置与时间）→ 找到（自然语言提问）**。因此图形不表达"设备"，而表达"本能"。

识别符优先级：大尾巴 > 尖耳 > 坐姿躯干 > 眼点。面部仅一个眼点、不设嘴部笔画，16px 下眼睛可消失，但尾巴与躯干轮廓必须成立。

## 二、文件清单

### SVG（首选，任意缩放不失真）

| 文件 | 尺寸 | 用途 |
| --- | --- | --- |
| `svg/logo-mark.svg` | 64×64 | 主图形，`currentColor`，可随文字色变化 |
| `svg/logo-mark-inverse.svg` | 64×64 | 白色图形，深色背景 |
| `svg/logo-mark-square.svg` | 64×64 | 黑底圆角方块（App 图标基底，圆角半径 15/64） |
| `svg/logo-lockup.svg` | 159×52 | 横版组合，导航栏 / 页脚 |
| `svg/logo-lockup-inverse.svg` | 159×52 | 白色横版组合，深色导航栏 |
| `svg/logo-lockup-stacked.svg` | 106×120 | 竖版组合，启动页 / 名片 / 海报 |

### PNG（透明通道，已含黑白两版）

- `png/mark-black/findy-mark-{512,256,128,64,32,16}.png`
- `png/mark-white/findy-mark-white-{512,256,128,64,32,16}.png`
- `png/app-icon/findy-app-{512,256,192,128,64,48,32,16}.png`（圆角已合成，四角透明）

### 其他

- `favicon.ico`：16 / 24 / 32 / 48 / 64 多尺寸
- `og-image-1200x630.png`：社交分享卡

## 三、接入方式

```html
<!-- 基础 favicon -->
<link rel="icon" href="/brand/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/brand/png/app-icon/findy-app-32.png">
<link rel="apple-touch-icon" sizes="192x192" href="/brand/png/app-icon/findy-app-192.png">
<link rel="manifest" href="/manifest.webmanifest">

<!-- 导航栏（随文字色变化） -->
<img src="/brand/svg/logo-lockup.svg" alt="Findy" width="159" height="52">
```

```html
<!-- 内联使用，可用 CSS 控制颜色 -->
<span class="logo" style="color:#111">
  <svg viewBox="0 0 64 64" width="28" height="28" aria-label="Findy">
    <path fill="currentColor" fill-rule="nonzero" d="…（取自 logo-mark.svg）"/>
  </svg>
</span>
```

```jsx
// React：以 SVG 作为组件，尺寸由 props 控制
export const FindyMark = ({ size = 28, ...rest }) => (
  <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Findy" {...rest}>
    <path fill="currentColor" fillRule="nonzero" d={MARK_PATH} />
  </svg>
);
```

## 四、最小尺寸

| 形态 | 最小尺寸 | 说明 |
| --- | --- | --- |
| 主图形 | 16px | 低于 16px 尾巴与躯干的间隙会消失 |
| 圆角方块图标 | 16px | 低于 16px 建议改用纯尾巴剪影 |
| 横版组合 | 120px 宽 | 低于 120px 请改用纯图形 |

## 五、安全留白

图形四周留白不小于**图形高度的 1/4**（64 画布中约 16 单位）。字标与图形之间的间距不得小于图形宽度的 1/4，禁止自行重排。

## 六、禁用规则

1. 不得改变图形比例、拉伸或压缩。
2. 不得旋转、倾斜、加描边、加投影、加渐变。
3. 不得改用黑白以外的颜色（品牌绿仅可用于辅助元素，不用于 logo）。
4. 不得置于低对比背景（如中灰、花纹照片）。
5. 不得拆解图形（尾巴、耳朵不可单独使用，除非另行定义子标记）。
6. 不得在图形内添加文字、表情或装饰。
7. 不得重新绘制字标字体——字标已转曲，需保持原比例。

## 七、待确认项

- 字标基于 Segoe UI Bold 转曲。若后续确定品牌专用字库，可替换为定制字形。
- 目前只提供黑白单色版；如需要双色（黑形 + 品牌绿点缀）版本，可在此路径下扩展 `logo-mark-green.svg`。
