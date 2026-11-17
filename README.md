# 中小学知识图谱（本地版）

把中小学知识图谱与自适应诊断搬进飞牛 fnOS 的本地应用：纯静态站点，零后端、零端口、零常驻进程，断网也能用。永久免费，无商业推广、无内购、无付费版本。

## 声明与署名

- 本仓库是「把开源项目 [cn-math-taxonomy](https://github.com/xiaoyang111222/cn-math-taxonomy) 静态站打包为飞牛 fnOS 应用」的壳工程，含其改编内容。原项目作者 **xiaoyang111222（@hassanyehiaa）**，原项目站点 [math.pansgo.com](https://math.pansgo.com/)，采用 [CC BY-NC 4.0（署名-非商业性使用 4.0 国际）](https://creativecommons.org/licenses/by-nc/4.0/deed.zh-hans) 许可。
- 原作者是所含知识图谱、题库、自适应前置诊断与站点页面的开发者；飞牛 fnOS 版本由 **许诺** 独立改编打包并发布，与原项目及其作者相互独立、无任何关联或背书关系；原项目与原作者不为本应用提供任何支持、服务或承诺。
- 禁止任何商业用途（付费课程、付费 App、机构收费服务、售卖题库等）。
- 原项目注明：先修关系、题库与册次目录的大量内容仍待一线教师审核，高中题与英语题未做盲解复核，请勿作为权威教学结论。

## 功能

- **知识图谱**：小学到高中 10 个学科（数学、语文、科学、道德与法治、历史、地理、生物、化学、英语、物理）的知识点与先修关系，按学段 / 年级 / 册次 / 章节筛选。
- **自适应前置诊断**：从目标知识点沿先修关系往回追溯出题，定位薄弱根因，输出按学习顺序排列的补学路径。
- **错题本与盲区再测**、**孩子档案**、**结果导出**（分享图 / JSON / PDF）。
- **匿名使用统计**（独立可插拔模块，默认关闭）：仅首次安装、每次打开、版本升级三类匿名事件，可随时一键关闭；不采集答题内容与任何可识别个人信息。

## 目录结构

| 路径 | 内容 |
|---|---|
| `manifest` | 应用清单（名称 / 版本 / 开发者与发布者 / 运行控制） |
| `app/ui/` | 桌面入口与 CGI 静态分发器 |
| `cmd/`、`config/`、`wizard/` | 生命周期脚本、运行配置、安装向导 |
| `overlay/` | 原创页面（关于 / 数据来源、改动清单）与统计适配层 |
| `tools/` | 构建、引用检查与合规校验脚本 |
| `build.sh` | 构建入口（组装 → 校验 → 打包） |
| `store-listing/` | 应用中心上架材料（截图与描述） |

## 构建

```bash
bash build.sh --release   # 正式版，产出 dist/cnmath-main-vX.Y.Z.fpk
bash build.sh             # 分支测试版，产出 dist/cnmath-vX.Y.Z.x.fpk
```

- 依赖 `fnpack`（放 `.tools/fnpack.exe`，见[飞牛开发者文档](https://developer.fnnas.com/docs/cli/fnpack/)）。
- 上游快照钉死在 `UPSTREAM_COMMIT`，构建时校验一致；裁剪与覆盖均绑定锚点，锚点不命中即失败。
- `overlay/assets/stats-endpoint.js` 为私有配置，不随仓库分发；缺失时构建产物为零统计版本（`--no-stats` 亦可显式指定）。
- 只有合规校验全部通过才允许产出 `.fpk`。

## 许可

双层适用，详见 [LICENSE](LICENSE)：

- 自研壳工程（manifest、cmd、config、ui、wizard、overlay、tools、build.sh、图标）：MIT License，Copyright © 2026 许诺。
- 上游站点内容与改编部分：CC BY-NC 4.0，Copyright © xiaoyang111222。
