# DSH Evidence Review 0.3.0-experimental.3

首次公开实验版：DSH每8次主模型输出进入目标/范围/方法核对；最多3次只读工具、4轮生成，形成一条提醒进入下一步。复用宿主前缀、模型与认证，不使用Jev。Linux/Node24.14.1/DSH0.2.2-rc.4为已验证环境。

| 正式报告指标 | 结果 |
|---|---:|
| 固定错误片段目标检出率 | 50.0%（3/6） |
| 原正常片段误提醒 | 0/8 |
| 补充WiDS正常片段误提醒 | 0/6 |
| 真实定期对照最终通过 | 有插件0/1；无插件0/1 |
| 该次总费用变化 | +7.7% |

**尚未证明最终任务收益。** 曾局部修复后复发；7例没有全部跑完当前版本纠偏，缺测不记成成功或失败。已见开发材料、单次运行、单一非盲裁定，不是LongDS官方分数或泛化保证。运行代码与冻结0.3.0逐字节一致。

[正式结果表及7例明细](https://github.com/lu-x1/dsh-evidence-review/blob/main/evaluation/RESULTS.md) · [方法](https://github.com/lu-x1/dsh-evidence-review/blob/main/METHOD.md) · [安装说明](https://github.com/lu-x1/dsh-evidence-review#安装与启用) · [反馈](https://github.com/lu-x1/dsh-evidence-review/issues)

下载tgz并解包，再运行dsh plugin --profile YOUR_PROFILE add /absolute/path/to/package。需要宿主可用的pnpm、bubblewrap及Python。标准profile链接布局启停测试已通过，干净在线安装尚未验证。包中不含原始轨迹、第三方数据或密钥。
