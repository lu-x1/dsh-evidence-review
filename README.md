# DSH Evidence Review

为DeepSeek Harness（DSH）提供定期目标、范围与方法核对。每8次主模型输出检查一次；发现有依据的冲突后，把提醒交给主Agent重算。支持最多3次只读工具求证，复用主请求前缀和宿主模型配置，不需要单独填写API Key，不使用Jev。

这是 **0.3.0-experimental.3 实验版**，运行代码等同冻结0.3.0。2026-11-25已更新扩测结果，全部10个错误及未跑项目列在[最新正式结果表](evaluation/expansion-02/RESULTS.md)；[旧v0.5结果](evaluation/RESULTS.md)原样保留。

| 指标 | 当前结果 |
|---|---:|
| 旧开发材料目标检出 | 3/6（50.0%） |
| 新增Kiva来源目标检出 | **0/3** |
| 当前方法已测错误检查点合计 | **3/9（33.3%）** |
| 正常检查点误提醒 | **0/15** |
| 固定检查点核对完成 | 22/24 |
| 旧FoodHub定期对照的最终通过 | 有插件0/1；无插件0/1，费用+7.7% |
| 新Kiva定期对照 | 已完成共同3题均2/3，第17题预算中断；未得完整收益 |

评测集现有25个检查点：10个错误、15个正常，覆盖8个数据来源；F26未单独重测，因此检出分母为9。新增3个错误点只来自一条Kiva轨迹、两种持续偏差，不能当作三个独立任务。核对未完成也计入检出分母。插件能促使部分局部重算，但仍会漏检、复发；当前证据未通过“解决大多数漂移、提高最终任务成功率”的验收。没有10例整体纠偏率，也不是LongDS官方总分或独立留出集成绩。

## 安装与启用

已验证环境为Linux、Node24.14.1、DSH0.2.2-rc.4、bubblewrap和Python3。其他操作系统、DSH版本暂未验证。DSH的插件安装命令还需要可用的pnpm。下载[Release](https://github.com/lu-x1/dsh-evidence-review/releases)中的tgz，解包到一个固定目录，然后运行：

```bash
tar -xzf dsh-evidence-review-0.3.0-experimental.3.tgz
dsh plugin --profile YOUR_PROFILE add /absolute/path/to/package
```

将YOUR_PROFILE和绝对路径替换为实际值。组合包声明见cordis.patch.yml。也可克隆本仓库，然后把仓库绝对路径传给同一个安装命令。单独解包并按绝对入口加载可能无法解析宿主共享依赖。

宿主已有的模型、认证和thinking设置由插件继承；要复现实验，主模型用DeepSeek官方deepseek-flash、thinking开启、reasoning effort high。在profile用户补丁中修改已有插件行的config即可调整默认设置：

```yaml
- id: dsh-evidence-review
  config:
    every: 8
    maxTokens: 16384
    timeoutMs: 120000
    maxToolCalls: 3
    maxRounds: 4
    toolTimeoutMs: 15000
    pythonExecutable: /usr/bin/python3
    reviewScope: current
    verifyDefinitions: false
```

停用时将该行设为disabled: true并重启DSH，或使用宿主的组合包移除流程。完整设计与工具边界见[METHOD.md](METHOD.md)。

## 查看效果与复核分数

在DSH原生会话中查找plugin:dsh-evidence-review/receipt事件，查看触发、结论、工具求证和提醒；提醒入队后还需核实被下一主请求消费。软提醒不会强制中断、回滚文件或保证后续一直遵守。

```bash
python3 evaluation/expansion-02/recompute_scores.py
npm test
```

第一个命令从公开逐例裁定核算分数及源码哈希，无外部依赖或模型费用。第二个运行包含真实DSH组件、只读工具隔离的机制测试，需要已安装开发依赖及Linux允许bubblewrap用户命名空间；测试用假模型，无付费调用。此前标准profile链接布局的实际启停测试通过；尚未验证干净环境的一键在线安装。

## 已知限制与反馈

核对可能漏掉公式定义、历史约束及已发生的偏移，也可能接受主Agent的错误解释。全前缀会增加时延，缓存不能保证命中；未知、超时和无最终结论均不算正常通过。只读工具访问的是实时文件视图，不保证并发数据快照一致。

欢迎在[Issues](https://github.com/lu-x1/dsh-evidence-review/issues)反馈漏检、误提醒、核对未完成、未修复或修复复发。请附DSH/Node版本、插件配置、脱敏要求、公开输出和相关收据，说明期望与实际结果；不要上传API Key、完整认证配置、私有推理或未授权数据。

MIT许可证用于本仓库代码与整理的报告。上游LongDS任务、数据和DSH运行时未随包复制，其权利与许可证归原提供方。[上游来源与版本](evaluation/provenance.json)。
