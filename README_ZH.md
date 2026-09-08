# 住下来的空间

**巴塞罗那旅游住房与居民租赁市场的空间关系**

Rongzhi Liang · 新加坡国立大学 · 2026 年 9 月  
[在线阅读](https://rongzhi-liang.github.io/room-to-live-barcelona-housing-and-tourism/) · [English](README.md)

一个包含十四章的中英文地图故事：旅游住房集中在哪里，与居民面对的租赁压力有多少重合，又需要经过哪些环节，才能成为可供长期居住的家？项目结合官方住房与租赁统计、Airbnb 房源观测和有文献记录的街区经历，分析巴塞罗那的 73 个街区。

在 66 个可比街区中，旅游住房登记密度与 2025 年租金水平的联系，比与 2022—2025 年租金涨幅的联系更强，Spearman 秩相关系数分别为 0.74 和 0.10。这些空间关系不能证明因果影响。

## 复现

参照环境：macOS、R 4.6.1、Python 3.13.1、Node.js 24.19.0、pnpm 11.19.0 和 QGIS 3.44.12。R 空间库为 GEOS 3.13.0、GDAL 3.8.5 和 PROJ 9.5.1。软件包版本固定在 `renv.lock` 和 `site/pnpm-lock.yaml`；Python 使用标准库。

从仓库根目录开始操作。确保 `PATH` 中能找到 `Rscript`、`node` 和 `pnpm`；程序会识别 `/Applications/QGIS.app`。安装在其他位置时，可通过 `RSCRIPT`、`NODE_BINARY`、`PNPM` 和 `QGIS_PYTHON` 指定可执行文件。

1. 如果 R 软件包版本不同，使用已安装的 `renv` 恢复：

   ```sh
   Rscript -e 'dir.create(".r-library", showWarnings=FALSE); renv::restore(lockfile="renv.lock", library=".r-library", prompt=FALSE)'
   ```

2. 将 `site/.env.example` 复制为 `site/.env.local`。在 `VITE_MAPBOX_TOKEN` 中填写允许预览网址访问的 Mapbox 公开令牌，保留 `VITE_MAPBOX_SOURCE_MODE=local`，以显示重建的 GeoJSON。
3. 重建并预览：

   ```sh
   python3 reproduce.py
   cd site
   pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort
   ```

打开 [127.0.0.1:4173](http://127.0.0.1:4173/)。固定版本的输入已包含在 `data/inputs.zip` 中；安装依赖和加载底图需要联网。程序校验数据与结果后，在 `build/research/` 生成研究结果，在 `build/qgis/` 生成 QGIS 工程，在 `build/mapbox/` 生成上传图层，并在 `site/dist/` 生成完整网站。

## 发布

构建本项目的 GitHub Pages 网站时，在仓库根目录运行：

```sh
python3 reproduce.py --base /room-to-live-barcelona-housing-and-tourism/
```

源文件保留在 `main` 分支。将 `site/dist/` 的内容及空白 `.nojekyll` 文件放入 `gh-pages` 分支根目录，然后在 GitHub Pages 设置中选择该分支。路径使用实际仓库名称，并在 Mapbox 令牌设置中允许发布后的网址访问。

如需使用自己账号中的 Mapbox Studio 图层，将 `build/mapbox/` 中四份 GeoJSON 上传为 tilesets，并更新 `site/public/mapbox/registry.json` 中的 `tilesetId` 和 `sourceLayer`。重新组装样式：

```sh
python3 analysis/assemble_style.py --base site/public/mapbox/base.style.json --registry site/public/mapbox/registry.json --data-dir site/public/data --out build/mapbox/room-to-live.style.json
```

将 `build/mapbox/room-to-live.style.json` 导入 Studio 并发布。把 Style URL 写入 `site/public/mapbox/production.json`，设置 `VITE_MAPBOX_SOURCE_MODE=published`，再重新编译。

## 来源与许可

[输入清单](data/inputs.json)记录来源日期、校验值和保留字段。Airbnb 与登记数据保留全部记录及所选字段的原值；原始租赁工作簿和行政边界文件保持原样。[来源目录](config/sources.json)收录故事引用的文献，[研究配置](config/study.json)记录分析参数。

| 内容 | 来源与许可 |
| --- | --- |
| Airbnb 房源观测 | [Inside Airbnb](https://insideairbnb.com/get-the-data/)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| 旅游住房登记与住宅数量 | 巴塞罗那市政府 · Open Data BCN，CC BY 4.0 |
| 行政边界 | 巴塞罗那市政府 · [CartoBCN](https://w20.bcn.cat/CartoBCN/)，[复用条款](https://w133.bcn.cat/geoportal/descargas/en_gb_cond_us_carto.pdf) |
| 租赁统计 | 加泰罗尼亚政府 / INCASÒL，[公共信息复用条款](https://web.gencat.cat/ca/avis-legal) |
| DM Sans 与 Instrument Serif 字体 | 原作者；SIL Open Font License 1.1，完整许可见 [fonts](site/public/fonts/) |
| Mapbox GL JS 与底图 | [Mapbox 条款](https://www.mapbox.com/legal/tos/)及软件包许可；保留 Mapbox 和 OpenStreetMap 贡献者署名 |

第三方材料保留各自的许可条件。复用数据时，应注明提供方及所作修改。新闻报道和公开文件通过链接与转述引用，仓库不收录整篇报道或出版方 PDF。
