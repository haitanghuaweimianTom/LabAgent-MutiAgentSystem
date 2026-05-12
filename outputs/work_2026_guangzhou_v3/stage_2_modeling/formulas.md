基于离散事件驱动与预期锚定理论，现行成品油调价机制可抽象为“信号输入-预期过滤-状态累积-区间调控”的混合动力学系统。为精准刻画价格传导的非对称性并破解政策干预的黑箱特征，模型引入行为经济学中的损失厌恶假说与参考点依赖理论，结合宏观稳态目标与行业基本面约束，构建具备严格马尔可夫性的状态转移框架。

设第 $t$ 个调价窗口期（步长 $\Delta \tau = 10$ 个工作日）的国际一揽子原油加权均价为 $\bar{P}_t$，其合成遵循基准权重规则：
$$
\bar{P}_t = \sum_{i=1}^{N} w_i P_{i,t} \quad (1)
$$
式中 $w_i$ 为第 $i$ 种基准原油的计价权重，满足 $\sum_{i=1}^N w_i = 1$ 且 $w_i \in [0,1]$。

针对传统线性映射忽略传导摩擦的缺陷，重构理论调价幅度 $\Delta D_t^{\text{theo}}$ 的生成机制。基于前景理论，市场主体对油价上涨的敏感度显著高于下跌，导致上行成本转嫁刚性更强。为此，引入符号依赖的分段弹性系数，构建如下非对称映射函数：
$$
\Delta D_t^{\text{theo}} = 
\begin{cases} 
\beta^+ \Delta \bar{P}_t + \varepsilon_t, & \Delta \bar{P}_t > 0 \\ 
\beta^- \Delta \bar{P}_t + \varepsilon_t, & \Delta \bar{P}_t \leq 0 
\end{cases} \quad (2)
$$
式中 $\Delta \bar{P}_t = \bar{P}_t - \bar{P}_{t-1}$ 为窗口期油价变动量；$\beta^+$ 与 $\beta^-$ 分别为油价上行与下行区间的传导弹性系数，且实证先验满足 $\beta^+ > \beta^- > 0$。该差异源于终端消费者的损失厌恶心理（对涨价容忍阈值低，预期粘性高）与炼厂成本核算的向下刚性。$\varepsilon_t \sim \mathcal{N}(0, \sigma_\varepsilon^2)$ 为涵盖汇率波动、税费调整及市场微观摩擦的白噪声扰动项。

为消除原机制中缓冲池阈值判断的逻辑冗余并保障状态转移的马尔可夫性，将累积、触发与清零过程统一至单一状态转移方程。定义缓冲池状态变量 $B_t$ 为跨期未释放的调价差额，其演化遵循软触发逻辑：
$$
B_t = \left( B_{t-1} + \Delta D_t^{\text{theo}} \right) \cdot \left[ 1 - \mathcal{S}\left( \frac{|B_{t-1} + \Delta D_t^{\text{theo}}| - 50}{\delta_B} \right) \right] \quad (3)
$$
式中 $\mathcal{S}(x) = (1+e^{-x})^{-1}$ 为Sigmoid平滑激活函数，$\delta_B$ 为阈值过渡带宽度参数。该设计在累积额逼近50元/吨时实现概率型释放，彻底消除硬截断导致的系统非连续跳跃。状态向量 $\mathbf{X}_t = (D_{t-1}, B_{t-1}, \bar{P}_t)^\top$ 仅依赖于上一期状态与当期输入，满足 $P(\mathbf{X}_t | \mathbf{X}_{t-1}, \dots, \mathbf{X}_0) = P(\mathbf{X}_t | \mathbf{X}_{t-1})$，严格确立马尔可夫链的无记忆性。

针对40美元/桶与130美元/桶的区间调控原则，摒弃绝对硬截断假设，引入贴合“原则上”政策弹性的渐变型调控函数。实际调价幅度 $\Delta D_t^{\text{act}}$ 的决策映射定义为：
$$
\Delta D_t^{\text{act}} = \alpha_t \cdot \left[ \Delta D_t^{\text{theo}} + \lambda B_{t-1} \cdot \mathcal{S}\left( \frac{|B_{t-1} + \Delta D_t^{\text{theo}}| - 50}{\delta_B} \right) \right] \cdot \Phi(\bar{P}_t) \quad (4)
$$
其中 $\lambda \in [0,1]$ 为历史缓冲存量释放权重；$\Phi(\bar{P}_t)$ 为区间软约束函数，采用双曲正切型概率截断：
$$
\Phi(\bar{P}_t) = 1 - \frac{1}{2} \left[ \tanh\left( \frac{40 - \bar{P}_t}{\delta_L} \right) \cdot \mathbb{I}(\bar{P}_t < 40) + \tanh\left( \frac{\bar{P}_t - 130}{\delta_H} \right) \cdot \mathbb{I}(\bar{P}_t > 130) \right] \quad (5)
$$
该函数在 $\bar{P}_t$ 处于正常区间时趋近于1，在逼近地板或天花板价时平滑衰减，$\delta_L, \delta_H$ 为政策弹性过渡带参数，精准还原调控机制的裁量空间。

为破解政策干预系数 $\alpha_t$ 的数据反演黑箱，构建融合宏观稳态与行业基本面的结构化决定方程。基于多目标动态规划框架，$\alpha_t$ 由通胀容忍度、炼厂合理利润与供应链安全三重约束共同驱动：
$$
\alpha_t = \frac{1}{1 + \exp\left( -\left[ \gamma_1 (\text{CPI}_t - \pi^*) + \gamma_2 (M_t - M^*) + \gamma_3 (\text{Inv}_t - \text{Inv}^*) \right] \right)} \quad (6)
$$
式中 $\text{CPI}_t$ 为当期居民消费价格指数，$\pi^*$ 为宏观通胀目标阈值；$M_t$ 为炼厂综合加工毛利，$M^*$ 为行业盈亏平衡基准线；$\text{Inv}_t$ 为战略原油商业库存天数，$\text{Inv}^*$ 为供应链安全警戒线。系数 $\gamma_1 < 0$ 表征通胀压力对提价的抑制作用，$\gamma_2 > 0$ 反映保供稳链对炼厂合理利润的托底需求，$\gamma_3 > 0$ 刻画库存缓冲对价格传导的平滑效应。该结构方程将政策意图显性化，使 $\alpha_t$ 具备明确的经济解释力与跨期可预测性。

最终，国内成品油最高零售限价 $D_t$ 的离散更新规则由下式闭合系统：
$$
D_t = D_{t-1} + \Delta D_t^{\text{act}} \quad (7)
$$
该混合逻辑动力学模型通过引入非对称分段弹性、软约束区间函数、统一马尔可夫型缓冲池转移及结构化政策系数，完整刻画了“信号输入-预期过滤-状态累积-弹性调控”的闭环传导路径。模型不仅有效剥离了历史调价中的噪声干扰，为拟合精度验证与非对称性实证检验提供了严密的数理基准，更为后续中东冲突极端情境下的动态优化策略仿真与多目标政策权衡奠定了可扩展的计算框架。

将成品油调价决策置于部分可观测马尔可夫决策过程（POMDP）框架下，以刻画政策制定者面对地缘冲突引发的市场噪声与信息滞后时的动态博弈特征。真实系统状态 $X_t$ 包含不可直接观测的宏观基本面与供应链隐性变量，决策主体仅能获取高频代理信号构成的观测向量 $O_t = [P_t^{\text{Wind}}, \Delta D_t^{\text{NDRC}}, \pi_t^{\text{CPI}}, V_t^{\text{RV}}]^\top$，分别对应Wind一篮子原油指数、发改委调价公告价差、核心CPI同比增速及基于高频收益率计算的已实现波动率。引入卡尔曼滤波与自适应预期更新机制构建信念状态 $b_t = \mathbb{P}(X_t|\mathcal{O}_t)$，其中预期冲击的演化遵循 $\hat{P}_{t+1|t} = \alpha P_t + (1-\alpha)\hat{P}_{t|t-1} + \eta_t$，$\alpha \in (0,1)$ 为学习速率，$\eta_t$ 为预期修正扰动。该设定有效放宽了完全信息假设，使模型能够内生处理政策透明度不足引发的市场摩擦。

设定离散时间尺度 $\Delta t = 1$，严格对应单次10个工作日的调价窗口期。国际基准油价 $P_t$ 的随机演化服从带跳跃的均值回归过程（Ornstein-Uhlenbeck-Jump）：
$$P_{t+1} = P_t + \kappa(\theta - P_t) + \sigma \epsilon_t + J_t \cdot \mathbb{I}_{\{N_t=1\}}, \quad \epsilon_t \sim \mathcal{N}(0,1) \tag{1}$$
式中 $\kappa$ 为均值回归速率，$\theta$ 为长期均衡价格锚，$\sigma$ 为扩散项波动率。跳跃幅度 $J_t \sim \mathcal{N}(\mu_J, \sigma_J^2)$，泊松计数过程 $N_t \sim \text{Poisson}(\lambda)$，$\lambda$ 为单位期跳跃强度，用于捕捉霍尔木兹海峡封锁等黑天鹅事件的脉冲冲击。

现行政策规则中的调价门槛、区间调控与缓冲池机制需转化为严格可计算的数学约束。设理论调价幅度为 $\Delta P_t^{\text{calc}} = \beta (P_t - P_{t-1})$，缓冲池累积差额为 $B_t$。实际调价决策 $u_t$ 的可行控制集 $\mathcal{U}_t$ 采用分段函数与逻辑指示函数联合界定，彻底消除原机制描述中的条件嵌套歧义：
$$u_t = \begin{cases} 
0, & \mathbb{I}_{\{|\Delta P_t^{\text{calc}} + \varphi B_t| < 50\}} = 1 \\
\min\left( D^{\text{ceil}} - D_t,\, \max\left( D^{\text{floor}} - D_t,\, \Delta P_t^{\text{calc}} + \varphi B_t \right) \right), & \mathbb{I}_{\{40 \le P_t \le 130,\, |\Delta P_t^{\text{calc}} + \varphi B_t| \ge 50\}} = 1 \\
\psi_{\text{floor}}(P_t) \cdot (\Delta P_t^{\text{calc}} + \varphi B_t), & \mathbb{I}_{\{P_t < 40\}} = 1 \\
\psi_{\text{ceil}}(P_t) \cdot (\Delta P_t^{\text{calc}} + \varphi B_t), & \mathbb{I}_{\{P_t > 130\}} = 1 
\end{cases} \tag{2}$$
其中 $\varphi \in [0,1]$ 为缓冲池释放系数，$\psi_{\text{floor}}(P_t) = \mathbb{I}_{\{P_t<40\}} \cdot 0$，$\psi_{\text{ceil}}(P_t) = \mathbb{I}_{\{P_t>130\}} \cdot \bar{\psi}$（$\bar{\psi}\in[0,1)$ 为天花板抑制因子）。该映射确保 $u_t \in \mathcal{U}_t$ 在任意油价路径下均具有唯一确定性，且边界条件满足 Lipschitz 连续性。

社会总福利损失函数 $L_t$ 由五项可微子目标加权构成。各子目标 $\ell_i$ 显式采用二次型或线性结构以保障梯度求解的数值稳定性：
\begin{align*}
\ell_1 &= \omega_1 \left( u_t - u_t^* \right)^2 + \eta_1 \max(0, u_t) \quad \text{(消费者福利损失，惩罚超额调价)} \\
\ell_2 &= \omega_2 \left( \pi^{\text{ref}} - (\alpha_{\text{crack}} P_t - u_t - C_{\text{op}}) \right)^2 \quad \text{(炼厂利润损失，裂解价差偏离惩罚)} \\
\ell_3 &= \omega_3 \left( \pi_t - \pi_{\text{target}} \right)^2 + \omega_3' |u_t| \cdot \xi_{\text{trans}} \quad \text{(CPI溢出效应，输入型通胀传导)} \\
\ell_4 &= \omega_4 \left( \hat{P}_{t+1|t} - \hat{P}_{t|t-1} - \Delta P_t^{\text{calc}} \right)^2 \quad \text{(预期冲击成本，政策信号一致性约束)} \\
\ell_5 &= \omega_5 \exp\left( -\frac{S_t - S_{\min}}{\delta} \right) + \omega_5' \mathbb{I}_{\{P_t > 130\}} (D^{\text{ceil}} - u_t)^2 \quad \text{(能源安全风险，库存安全垫与需求抑制)}
\end{align*}
总损失标量函数为 $L_t(X_t, u_t) = \sum_{i=1}^5 \ell_i$，所有分量关于控制变量 $u_t$ 连续可微，满足动态规划中 Hamilton-Jacobi-Bellman 方程的解析求解条件。

针对核心动力学参数 $\Theta = \{\kappa, \theta, \sigma, \lambda, \mu_J, \sigma_J\}$，构建基于高频代理数据的广义矩估计（GMM）与极大似然估计（MLE）混合方案。选取2016-2025年Wind布伦特原油日线序列、发改委历次调价公告价差及国家统计局月度核心CPI同比数据构建样本矩。定义理论矩条件向量 $\mathbb{E}[g(X_t, \Theta)] = \mathbf{0}$，其中：
$$g_1 = P_{t+1} - P_t - \kappa(\theta - P_t), \quad g_2 = g_1^2 - \sigma^2, \quad g_3 = \mathbb{I}_{\{|P_{t+1}-P_t| > 3\sigma\}} - \lambda \tag{3}$$
通过最小化加权二次型 $Q(\Theta) = \bar{g}_T(\Theta)^\top W_T \bar{g}_T(\Theta)$ 获得一致估计量 $\hat{\Theta}_{\text{GMM}}$。对于跳跃分布参数 $(\lambda, \mu_J, \sigma_J)$，采用MLE对已识别的极端波动子样本（如2020Q1、2022Q1及2026Q1冲突期）进行分段对数似然最大化：
$$\mathcal{L}_{\text{MLE}}(\Theta) = \sum_{t=1}^T \ln \left[ (1-\lambda)\phi\left(\frac{\Delta P_t - \kappa(\theta-P_t)}{\sigma}\right) + \lambda \int \phi\left(\frac{\Delta P_t - \kappa(\theta-P_t) - j}{\sigma}\right) f_J(j) dj \right] \tag{4}$$
该混合估计策略有效分离了常规扩散噪声与地缘冲击尾部风险，确保模型在平稳期与危机期的参数稳健性。

综合上述设定，成品油调价机制的动态优化严格形式化为POMDP框架下的跨期最优控制问题。在信念状态 $b_t$ 下，求解最优反馈策略 $\pi^*(b_t)$：
$$\min_{\{u_\tau\}_{\tau=t}^T} J(b_t) = \mathbb{E}\left[ \sum_{\tau=t}^T \gamma^{\tau-t} L_\tau(X_\tau, u_\tau) \;\middle|\; b_t \right] \quad \text{s.t. } u_\tau \in \mathcal{U}_\tau, \; X_{\tau+1} \sim \mathcal{T}(X_\tau, u_\tau, \xi_\tau) \tag{5}$$
其中 $\gamma \in (0.95, 0.99)$ 为跨期贴现因子，$\mathcal{T}(\cdot)$ 为状态转移核。利用近似动态规划（ADP）结合滚动时域模型预测控制（MPC），在每次调价窗口前基于 $b_t$ 生成未来 $H$ 期最优调价轨迹 $\{u_t^*, u_{t+1}^*, \dots, u_{t+H-1}^*\}$，仅执行首期决策后重新观测并更新信念状态。该闭环控制架构在严格遵循政策硬约束的前提下，实现了消费者福利、产业利润、宏观通胀、预期管理与能源安全五重目标的动态帕累托最优。

为构建兼具理论严谨性与公众可理解性的成品油动态调价机制，本节首先重构可观测状态空间与符号体系，进而显式刻画社会福利损失函数，并通过策略蒸馏与分布鲁棒优化（DRO）框架提取阶梯式透明规则，最终给出面向极端不确定性的机制改进路径。

**一、 符号系统与可观测代理变量重构**
为消除上下文歧义，本文严格区分跨期折现参数与规则调节系数。设 $\delta \in (0,1)$ 为社会福利折扣因子，$\boldsymbol{\kappa}=(\kappa_1, \kappa_2, \kappa_3)^\top$ 为显式调价规则系数向量，$\rho \ge 0$ 为Wasserstein分布鲁棒半径，$K>0$ 为Lipschitz常数。原模型中的隐状态向量被替换为公开可获取的代理指标集合 $Z_t = (S_t^{\text{avg}}, \text{VIX}_t, Q_t^{\text{imp}}, \pi_t^{\text{cpi}})^\top$，其中：$S_t^{\text{avg}}$ 为发改委官方公布的10个工作日布伦特原油均价；$\text{VIX}_t$ 为原油期权隐含波动率指数（或CBOE VIX替代）；$Q_t^{\text{imp}}$ 为海关总署月度原油进口量（经季节性调整）；$\pi_t^{\text{cpi}}$ 为国家统计局公布的CPI同比增速。该代理向量完全可观测，满足监管透明与公众验证要求。

**二、 福利损失函数构建与凸性论证**
单期社会福利损失函数 $L(Z_t, u_t)$ 由价格传递偏离成本、炼厂利润波动成本与通胀溢出成本三部分构成，其显式表达式为：
$$
L(Z_t, u_t) = \omega_1 \left( u_t - \gamma_0 \Delta S_t^{\text{avg}} \right)^2 + \omega_2 \left( \frac{u_t}{P_{t-1}} \right)^2 + \omega_3 \left[ \max\left(0, \xi u_t - \bar{\pi}_{\text{cpi}}\right) \right]^2 \tag{1}
$$
其中 $u_t = \Delta P_t$ 为当期调价幅度，$\gamma_0$ 为理论完全传递系数，$\xi$ 为油价向CPI的传导弹性，$\bar{\pi}_{\text{cpi}}$ 为通胀容忍阈值，$\omega_i > 0$ 为权重参数。凸性假设依据如下：(1) 二次项 $\left( u_t - \gamma_0 \Delta S_t^{\text{avg}} \right)^2$ 与 $\left( u_t/P_{t-1} \right)^2$ 关于 $u_t$ 的海森矩阵恒为正定，严格凸；(2) 铰链函数 $\max(0, \cdot)$ 为凸函数，其与线性映射的复合仍保持凸性，平方运算进一步保持凸性；(3) 凸函数的非负加权和仍为凸函数。宏观政策文献（如Barro-Gordon型损失函数）与实证校准均表明，该二次-铰链复合形式在合理参数域内满足局部Lipschitz连续性，为后续对偶推导提供数学基础。

**三、 透明调价规则的策略蒸馏模型**
将高维隐式最优策略 $\pi^*(Z_t)$ 映射至低维显式规则 $\pi_{\boldsymbol{\kappa}}(Z_t)$，构建带稀疏惩罚的蒸馏优化问题：
$$
\min_{\boldsymbol{\kappa} \in \mathcal{K}} \quad \mathbb{E}_{P_0} \left[ \frac{1}{T}\sum_{t=0}^{T-1} \delta^t \left\| \pi_{\boldsymbol{\kappa}}(Z_t) - \pi^*(Z_t) \right\|^2 \right] + \lambda \|\boldsymbol{\kappa}\|_1 \tag{2}
$$
$$
\text{s.t.} \quad \pi_{\boldsymbol{\kappa}}(Z_t) = \text{clip}\left( \kappa_1 S_t^{\text{avg}} + \kappa_2 \mathbb{I}(\text{VIX}_t > \tau_v) \text{VIX}_t + \kappa_3 \Delta P_{t-1}, \, \underline{P}, \overline{P} \right) \tag{3}
$$
式(2)第一项度量名义分布 $P_0$ 下显式规则对最优策略的拟合偏差，第二项 $L_1$ 惩罚促使系数稀疏化，防止规则过度参数化。式(3)将控制律显式化为“基准跟随+波动率阈值触发+方向惯性修正”的透明结构，动态截断边界 $\text{clip}(\cdot)$ 对应现行40/130美元区间调控的物理约束。

**四、 分布鲁棒性检验与Wasserstein对偶定理适用条件**
为检验规则在波动率分布漂移与极端冲突下的稳健性，引入Wasserstein分布鲁棒优化。设名义分布 $P_0$ 由历史区制转换跳跃扩散过程生成，模糊集定义为 $\mathcal{B}_\rho(P_0) = \{ Q : W_1(Q, P_0) \le \rho \}$。鲁棒目标为：
$$
V_{\text{rob}}(\boldsymbol{\kappa}) = \sup_{Q \in \mathcal{B}_\rho(P_0)} \mathbb{E}_Q \left[ L(Z, u(\boldsymbol{\kappa})) \right] \tag{4}
$$
根据Kuhn-Wasserstein对偶定理，该问题存在强对偶的严格适用条件为：损失函数 $L(z, u)$ 关于状态 $z$ 满足 $K$-Lipschitz连续性，即 $\forall z, z', |L(z,u)-L(z',u)| \le K \|z-z'\|$。由于式(1)含二次增长项，在全空间上不满足全局Lipschitz条件。本文引入紧致支撑假设（国际油价在 $[S_{\min}, S_{\max}]$ 内波动）或采用Huber平滑近似：
$$
\tilde{L}(z,u) = \begin{cases} 
L(z,u), & \|z\|_2 \le M \\
L(M,u) + \nabla_z L(M,u)^\top (z-M), & \|z\|_2 > M
\end{cases} \tag{5}
$$
经平滑后，$\tilde{L}$ 在全局满足Lipschitz常数 $K=\max_{\|z\|\le M} \|\nabla_z L(z,u)\|_2$。在此条件下，式(4)等价于有限维对偶问题：
$$
\inf_{\lambda \ge 0} \left\{ \lambda \rho + \mathbb{E}_{P_0} \left[ \sup_{z \in \mathcal{Z}} \left\{ \tilde{L}(z, u(\boldsymbol{\kappa})) - \lambda \|z - Z_0\|_2 \right\} \right] \right\} \tag{6}
$$
该形式将无限维分布偏移转化为单变量 $\lambda$ 的凸优化，可通过次梯度法高效求解，从而量化不同 $\rho$ 下的最坏情景福利损失。

**五、 从CVaR与Wasserstein半径到阶梯式触发规则及公众解读指南**
为提升政策可接受度，将复杂的CVaR尾部风险度量与Wasserstein半径 $\rho$ 映射为直观的“波动率分档调节系数”。设 $\text{VIX}_t$ 为分档依据，构建阶梯规则：
- **平稳档**（$\text{VIX}_t \le 18$）：$\rho = 0.02$，$\kappa_1=0.95$，$\kappa_2=0$，全额传导，CVaR缓冲系数 $\alpha=1.0$；
- **震荡档**（$18 < \text{VIX}_t \le 30$）：$\rho = 0.05$，$\kappa_1=0.80$，$\kappa_2=0.15$，触发部分平滑，$\alpha=0.75$；
- **极端档**（$\text{VIX}_t > 30$）：$\rho = 0.10$，$\kappa_1=0.50$，$\kappa_2=0.40$，启动阶梯熔断与累加冲抵，$\alpha=0.50$。

**公众解读指南**：当国际油价波动处于“平稳期”时，国内油价将按95%比例紧跟国际市场，保障市场信号传导；进入“震荡期”后，机制自动引入15%的波动率缓冲系数，降低调价频率与幅度，避免短期情绪放大；若遭遇地缘冲突导致“极端波动”，规则将切换至50%基准传导并叠加40%的波动抑制项，同时启用50元门槛的累加机制，确保民生用能成本可控。该规则无需复杂公式即可通过分档阈值直观验证，实现“算法黑箱”向“政策白盒”的转化。

**六、 机制改进建议**
基于上述建模与鲁棒检验，提出三项机制优化路径：其一，建立动态Wasserstein半径校准机制，将 $\rho$ 与VIX指数及霍尔木兹海峡航运保险溢价挂钩，实现分布漂移的自适应响应；其二，将现行固定40/130美元区间升级为“波动率弹性边界”，在极端冲突期引入成品油价格稳定调节基金进行跨期平滑，替代行政性暂停调价；其三，公开官方调价计算均价的权重构成与 $\kappa$ 系数校准日志，定期发布DRO最坏情景压力测试报告，以透明化对冲预期博弈，提升调控机制的公信力与抗冲击韧性。