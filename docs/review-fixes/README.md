# 评审整改差异包（最新：06e182a → ed12955）

> 用途：把「外部评审整改 + 边表 fallback」的差异单独打包，方便 P2/同事**只审阅差异**，
> 或在旧版本上应用补丁。完整代码、报告与测试已在 `main` 的 `ed12955`；
> 本目录只是差异副本，不替代仓库。

## 内容

| 文件 | 说明 |
| --- | --- |
| `评审整改-06e182a..ed12955.patch` | **累计补丁**：从整改前基线到当前 HEAD（SHA-256 `5776f744b7a42960ce091ca31e08d1c2fad826d1ac0b3ed37ebeeefc32a3e13a`） |
| `增量-b641db7..ed12955.patch` | **本次增量**：评审整改版 → 当前 HEAD（SHA-256 `f5c1cb027a9cdfebe7b804ed0e084d08cf6f528c4c228460ec06e67b767a1907`） |
| `diffstat.txt` | 累计 `git diff --stat 06e182a..ed12955`（与补丁同口径） |
| `incremental-diffstat.txt` | 增量 `git diff --stat b641db7..ed12955` |
| `binary-files.json` | 报告 docx/pdf 在 `ed12955` 的大小与 SHA-256（文本补丁不含二进制） |

> 补丁**不含** `reports/`（docx/pdf）与 `docs/review-fixes/`（本目录自身），避免二进制与递归引用。

## 版本关系

- `06e182a`：外部评审前的上一版（可调用接口、报告 34 页）
- `b641db7`：评审整改版（P2 兼容、双权重/线路速度、BFS 口径、bench 默认输出；报告 35 页；55 测试）
- `ed12955`：当前 HEAD（在上一版基础上新增「线条目缺站序时从 `graph.edges` 反推」；62 测试）

## 如何审阅

```powershell
git fetch origin
git diff --stat 06e182a..ed12955
git diff 06e182a..ed12955 -- core ui tests
git show ed12955 --stat
```

## 如何应用

### A. 从评审前基线一次性更新（推荐）

```powershell
git switch -c review-fixes 06e182a
git apply docs/review-fixes/评审整改-06e182a..ed12955.patch
git checkout ed12955 -- "reports/城市交通路径导航系统_实验报告.docx" "reports/城市交通路径导航系统_实验报告.pdf"
```

### B. 已应用上一版补丁（b641db7）后只加增量

```powershell
git apply docs/review-fixes/增量-b641db7..ed12955.patch
git checkout ed12955 -- "reports/城市交通路径导航系统_实验报告.docx" "reports/城市交通路径导航系统_实验报告.pdf"
```

## 校验

- 累计补丁 SHA-256：`5776f744b7a42960ce091ca31e08d1c2fad826d1ac0b3ed37ebeeefc32a3e13a`
- 增量补丁 SHA-256：`f5c1cb027a9cdfebe7b804ed0e084d08cf6f528c4c228460ec06e67b767a1907`
- 应用后：`python -m unittest discover -s tests -v`（**62/62**）、
  `python main.py --check --no-gui`（9 PASS + 1 SKIP）、`python tools/check_report.py`（22/22）。
- 两个补丁均已用 `git apply --check` 在对应基线上验证可干净应用。
- 逐项整改说明见 [`../评审整改记录-2026-10-18.md`](../评审整改记录-2026-10-18.md)。
