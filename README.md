# DSH Evidence Review

为DeepSeek Harness（DSH）提供定期目标、范围与方法核对。每8次主模型输出检查一次；发现有依据的冲突后，把提醒交给主Agent重算。支持最多3次只读工具求证，复用主请求前缀和宿主模型配置，不需要单独填写API Key，不使用Jev。

这是 **0.3.0-experimental.3 实验版**，默认运行代码仍等同冻结0.3.0。主对照是独立要求卡的24点两组开发试验，完整9个错误和15个正常点见[结果表与失败分析](evaluation/requirements-card-01/RESULTS.md)。要求卡及后续状态表探针均未并入默认插件。

| 最新同批对照 | R0：原核对 | R1：加独立要求卡 |
|---|---:|---:|
| 在时限内形成指定目标提醒 | **3/9** | **4/9†** |
| 不计修复建议不完整的提醒 | 3/9 | 3/9 |
| 正常点误提醒 | 0/15 | 0/15 |
| 正常点完成并判断正常 | 14/15 | 13/15 |
| 全部核对完成 | 20/24 | 20/24 |
| 组件API费用（含提取、失败调用） | $0.380163 | $0.615204（+61.8%） |

†新版F10指出了范围问题，但纠正建议仍可能只扩大到16个变化组，未明确恢复完整84组；排除该条后为3/9。L18的差异包含原版引用转义失败；两组实际都已识别门槛错误。不能把这一条当作要求卡提高理解能力的证据。要求卡只有16/24次可用，未证明稳健净收益。

评测库现有25个检查点（10错误、15正常），覆盖8个数据来源；本轮固定重测24点，F26在调用前排除，错误分母为9。全部是已见开发数据，单次配对，无独立留出集；K18/K19关联且有生效语义疑点。该分数是端点发现并形成提醒，**没有本轮修复、保持修复或全任务收益分数**。当前未通过“解决大多数漂移”的验收。

另已完成[低推理6点、代码出处索引8点及缓存控制探针](evaluation/followup-probes-01/RESULTS.md)：低推理目标提醒2/4、正常完成1/2；代码索引目标提醒2/5、正常完成3/3。索引未解决Kiva公式、水质分母和NFL定义三个预选难例；低推理另有一条超时后误报，未交付但保留风险记录。这些已见小样本探索未启用默认配置，也不拼接进上述24点分数。

最新[逐项比较、压缩视图及计时诊断](evaluation/context-diagnostics-01/RESULTS.md)也未通过筛选：逐项指令1/3目标提醒；压缩high为0/5、low为1/5（含一个预算截断点），low有1/3正常误提醒。压缩后Kiva和水质的迟到结论开始识别目标，但实验日志落盘等开销也被计入120秒，不能直接视为原生延迟。已在零API本地测试中验证独立日志/计时修复，旧分数保留，尚无修复后的核对器实网或全任务成绩；后续提取试验见下文。

另已完成[需求状态提取的6点可行性试验](evaluation/requirement-state-01/RESULTS.md)：要求侧、实现侧各6次，共12次，**可用JSON 0/12**；全部耗尽8192输出额度，10次公开内容为空、2次截断，费用$0.134439。按预定门槛停止后续36次。新日志/计时封装已用于这批真实提取；这不是修复后核对器的检出分数。通用状态内核的25项机制测试通过，但自动提取和语义对齐没有通过可行性验证，均未接入默认插件。

后续[轻量定义提取完整6点对照](evaluation/light-extraction-01/completed-01/RESULTS.md)已补完24份输入：低强度思考12/12可用，关闭思考11/12可用；这是提取交付成绩。内容复核仍有关键定义漏提取，关闭思考还在正常节点错用过期要求，未并入默认插件。24份模型答复估算费共$0.089332200，旧402另保留$0.018885，不计为已发生费用。原部分结果及失败均保留；没有新增检出或纠偏分数。

最新完成[轻量核对状态表6点真实对照](evaluation/commitment-monitor-01/RESULTS.md)：直接复用核对器公开结果维护暂定解释及未解决问题，无单独提取调用；3条已见轨迹、3错3正常。原版与状态表版目标提醒均2/3，正常误提醒均0/3、完成均6/6；状态表费增加16.4%，未启用默认。水质仍沿用错误分母；状态有出处不等于解释正确。该整包探针只有一个错误点拿到前次状态，未独立归因持久化；没有主Agent续跑，**不是纠偏率**。公开通用实现、全部逐点判定及脱敏usage供免费复核，不与上面24点拼接。

随后[剩余18点快速扩查](evaluation/commitment-monitor-quick-01/RESULTS.md)已结束：新增S实际17点、31次请求，最后1正常点预算未发起；合并前轮后23/24点已调用，9个目标错误均已检查，5个形成正确提醒、2个漏检、2个未完成。14个已调用正常点中12个完成、0个交付误提醒；另1条格式问题可零API兼容恢复，原成绩保留。新增6个错误S为3/6，历史原版对应也是3/6，没有新增检出证据；历史参照不是新同期两组对照。新增估算$0.275311104，未启用状态表为默认，未测本轮真实纠偏。完整清单、全部9错表和脱敏usage均公开。


[历史v0.6扩测](evaluation/expansion-02/RESULTS.md)与[更早v0.5结果](evaluation/RESULTS.md)原样保留，不跨批次挑最好数字。旧FoodHub真实定期对照最终两组均未通过；Kiva续跑不完整，仍未证明最终任务收益。另行实现的引用兼容候选通过44项本地机制测试；本批保存输出的零API重放恢复1条引用失败，这是兼容性验证，未并入默认代码，也不是新模型纠偏成绩。

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

在当前仓库根目录运行：

```bash
python3 evaluation/requirements-card-01/recompute_scores.py
python3 evaluation/followup-probes-01/recompute_scores.py
python3 evaluation/context-diagnostics-01/recompute_scores.py
python3 evaluation/requirement-state-01/recompute_scores.py
python3 evaluation/commitment-monitor-01/recompute_scores.py
python3 evaluation/commitment-monitor-quick-01/recompute_scores.py
python3 evaluation/expansion-02/recompute_scores.py
npm test
```

前七个命令分别复核主对照、后续探针、上下文诊断、提取试验、状态表探针、快速扩查与历史公开逐例分数、费用或源码哈希，无模型费用。最后一个运行包含真实DSH组件、只读工具隔离的机制测试，需要已安装开发依赖及Linux允许bubblewrap用户命名空间；测试用假模型，无付费调用。此前标准profile链接布局的实际启停测试通过；尚未验证干净环境的一键在线安装。

## 已知限制与反馈

核对可能漏掉公式定义、历史约束及已发生的偏移，也可能接受主Agent的错误解释。全前缀会增加时延，缓存不能保证命中；未知、超时和无最终结论均不算正常通过。只读工具访问的是实时文件视图，不保证并发数据快照一致。

欢迎在[Issues](https://github.com/lu-x1/dsh-evidence-review/issues)反馈漏检、误提醒、核对未完成、未修复或修复复发。请附DSH/Node版本、插件配置、脱敏要求、公开输出和相关收据，说明期望与实际结果；不要上传API Key、完整认证配置、私有推理或未授权数据。

MIT许可证用于本仓库代码与整理的报告。上游LongDS任务、数据和DSH运行时未随包复制，其权利与许可证归原提供方。[上游来源与版本](evaluation/provenance.json)。
