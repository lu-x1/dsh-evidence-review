# DSH Evidence Review

为DeepSeek Harness（DSH）提供定期目标、范围与方法核对。每8次主模型输出检查一次；发现有依据的冲突后，把提醒交给主Agent重算。支持最多3次只读工具求证，复用主请求前缀和宿主模型配置，不需要单独填写API Key，不使用Jev。

这是 **0.3.0-experimental.3 实验版**，运行代码等同冻结0.3.0。当前可公布的效果如下，详细案例和未跑项目全部列在[正式结果表](evaluation/RESULTS.md)。

| 指标 | 当前结果 |
|---|---:|
| 固定错误片段的目标检出率 | **50.0%（3/6）** |
| 原正常片段误提醒率 | **0.0%（0/8）** |
| 新WiDS正常片段误提醒（同一任务，补充结果） | 0/6 |
| 真实定期对照的最终任务通过 | 有插件0/1；无插件0/1 |
| 该次对照观察到的总费用变化 | +7.7% |

插件已能发现部分范围错误，提醒能促使局部重算；但当轮改对后仍可能复发。目前没有证据证明提高最终任务成功率。7个已知错误没有全部完成当前版本纠偏，未跑项没有计成失败或成功。这些是已见开发材料的小样本结果，既不是LongDS官方总分，也不是未见任务泛化成绩。

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
python3 evaluation/recompute_scores.py
npm test
```

第一个命令从公开逐例裁定核算分数及源码哈希，无外部依赖或模型费用。第二个运行包含真实DSH组件、只读工具隔离的机制测试，需要已安装开发依赖及Linux允许bubblewrap用户命名空间；测试用假模型，无付费调用。此前标准profile链接布局的实际启停测试通过；尚未验证干净环境的一键在线安装。

## 已知限制与反馈

核对可能漏掉公式定义、历史约束及已发生的偏移，也可能接受主Agent的错误解释。全前缀会增加时延，缓存不能保证命中；未知、超时和无最终结论均不算正常通过。只读工具访问的是实时文件视图，不保证并发数据快照一致。

欢迎在[Issues](https://github.com/lu-x1/dsh-evidence-review/issues)反馈漏检、误提醒、核对未完成、未修复或修复复发。请附DSH/Node版本、插件配置、脱敏要求、公开输出和相关收据，说明期望与实际结果；不要上传API Key、完整认证配置、私有推理或未授权数据。

MIT许可证用于本仓库代码与整理的报告。上游LongDS任务、数据和DSH运行时未随包复制，其权利与许可证归原提供方。[上游来源与版本](evaluation/provenance.json)。
