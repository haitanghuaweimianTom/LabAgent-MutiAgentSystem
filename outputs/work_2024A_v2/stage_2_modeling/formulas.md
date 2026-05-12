等距螺线盘入运动学建模与数值求解

## 一、变量与参数定义

| 类别 | 符号 | 含义 | 单位/备注 |
|:---|:---|:---|:---|
| **几何参数** | $p$ | 螺距 | $0.55$ m |
| | $a$ | 螺线系数 | $a = \frac{p}{2\pi} \approx 0.0875$ m/rad |
| | $r_0$ | 初始半径（第16圈） | $r_0 = 16p = 8.8$ m |
| | $L_i$ | 第 $i$ 节板凳长度 | $L_1 = 3.41$ m（龙头），$L_i = 2.20$ m（$i \geq 2$） |
| | $d$ | 孔中心到板端距离（前伸长度） | $0.275$ m |
| | $D$ | 孔径（把手直径） | $0.055$ m |
| **运动参数** | $v_h$ | 龙头前把手速度 | $1$ m/s（恒定） |
| | $\theta(t)$ | 从初始位置顺时针转过的角度 | rad |
| **系统变量** | $n$ | 板凳总节数 | $223$ |
| | $N$ | 把手点总数 | $N = 224$ |
| | $P_j$ | 第 $j$ 个把手点位置 | $j = 0, 1, \ldots, 223$ |
| | $l_j$ | 第 $j$ 节板凳的孔间距 | $l_1 = 2.86$ m，$l_j = 1.65$ m（$j \geq 2$） |
| | $\phi_j$ | 相邻板凳夹角（第 $j$ 节与第 $j+1$ 节） | rad |
| **辅助变量** | $s(\theta)$ | 螺线弧长函数 | m |
| | $t$ | 时间 | s |

---

## 二、核心数学模型建立

### 2.1 等距螺线几何约束与坐标系定义

建立平面直角坐标系：原点 $O$ 为盘入螺线中心，$x$ 轴正方向指向龙头初始位置，$y$ 轴按右手系确定。龙头顺时针盘入，故极角 $\theta$ 定义为从初始位置顺时针转过的角度，极径随 $\theta$ 增加而线性递减。

等距螺线（阿基米德螺线）方程采用以下形式以避免负半径问题：

$$\boxed{r(\theta) = a(\Theta_{\text{total}} - \theta) = r_0 - \frac{p}{2\pi}\theta} \tag{1}$$

其中 $\Theta_{\text{total}} = \frac{2\pi r_0}{p} = 32\pi$ rad 为螺线总张角，$\theta \in [0, \Theta_{\text{total}}]$ 保证 $r \geq 0$。当 $\theta = 0$ 时 $r = r_0 = 8.8$ m（第16圈起始位置）；当 $\theta = \Theta_{\text{total}}$ 时 $r = 0$（螺线中心）。

**物理意义**：式(1)中参数 $a = \frac{p}{2\pi} \approx 0.0875$ m/rad 表征螺线"松紧"程度。每顺时针转过 $2\pi$ rad，极径减小一个螺距 $p = 0.55$ m，形成等距螺旋结构。采用 $\Theta_{\text{total}} - \theta$ 的表述形式，使得 $\theta$ 的物理意义明确为"已转过的角度"，且天然保证半径非负。

直角坐标参数方程为：

$$\boxed{\begin{cases} x_0(\theta) = r(\theta)\cos\theta = \left(r_0 - \frac{p}{2\pi}\theta\right)\cos\theta \\ y_0(\theta) = r(\theta)\sin\theta = \left(r_0 - \frac{p}{2\pi}\theta\right)\sin\theta \end{cases}} \tag{2}$$

**物理意义**：式(2)将极坐标转换为直角坐标。需注意此处 $\theta$ 为顺时针转角，故三角函数形式与标准逆时针极坐标一致，这是由右手坐标系中顺时针旋转的等价表示所决定的。

### 2.2 弧长参数化与龙头运动学

螺线弧长微元由欧氏度量确定。对于参数曲线 $(r(\theta)\cos\theta, r(\theta)\sin\theta)$，弧长微元为：

$$\mathrm{d}s = \sqrt{\mathrm{d}x^2 + \mathrm{d}y^2} = \sqrt{r^2 + \left(\frac{\mathrm{d}r}{\mathrm{d}\theta}\right)^2}\,\mathrm{d}\theta \tag{3}$$

将 $r = r_0 - a\theta$ 和 $\frac{\mathrm{d}r}{\mathrm{d}\theta} = -a$ 代入：

$$\boxed{\mathrm{d}s = \sqrt{(r_0 - a\theta)^2 + a^2}\,\mathrm{d}\theta = \sqrt{r^2(\theta) + a^2}\,\mathrm{d}\theta} \tag{4}$$

**物理意义**：式(4)中 $r^2(\theta)$ 项反映切向运动贡献（沿圆周方向），$a^2$ 项反映径向运动贡献（向心收缩）。对于本问题，典型半径 $r \sim 5$ m 远大于 $a \approx 0.09$ m，故切向项占主导，但径向项在靠近中心时相对重要性逐渐增强。

弧长函数为积分形式：

$$\boxed{s(\theta) = \int_0^\theta \sqrt{(r_0 - a\varphi)^2 + a^2}\,\mathrm{d}\varphi} \tag{5}$$

该积分可通过换元 $u = r_0 - a\varphi$ 化为标准形式。令 $u = r_0 - a\varphi$，$\mathrm{d}u = -a\,\mathrm{d}\varphi$，得：

$$s(\theta) = -\frac{1}{a}\int_{r_0}^{r_0-a\theta}\sqrt{u^2+a^2}\,\mathrm{d}u = \frac{1}{a}\int_{r(\theta)}^{r_0}\sqrt{u^2+a^2}\,\mathrm{d}u \tag{6}$$

利用积分公式 $\int\sqrt{u^2+c^2}\,\mathrm{d}u = \frac{u}{2}\sqrt{u^2+c^2} + \frac{c^2}{2}\ln|u+\sqrt{u^2+c^2}|$，得到闭式解：

$$\boxed{s(\theta) = \frac{1}{2a}\left[r_0\sqrt{r_0^2+a^2} - r(\theta)\sqrt{r^2(\theta)+a^2} + a^2\ln\frac{r_0+\sqrt{r_0^2+a^2}}{r(\theta)+\sqrt{r^2(\theta)+a^2}}\right]} \tag{7}$$

**物理意义**：式(7)给出了弧长与极角的精确解析关系。第一项 $r_0\sqrt{r_0^2+a^2}$ 为初始位置贡献，第二项为当前位置贡献，第三项对数项反映螺线曲率累积效应。

龙头前把手以恒定速率 $v_h = 1$ m/s 运动，故运动学约束为：

$$\boxed{\frac{\mathrm{d}s}{\mathrm{d}t} = v_h = 1\,\text{m/s}} \tag{8}$$

结合式(4)与链式法则，得到极角演化方程：

$$\boxed{\frac{\mathrm{d}\theta}{\mathrm{d}t} = \frac{v_h}{\sqrt{r^2(\theta)+a^2}} = \frac{1}{\sqrt{(r_0-a\theta)^2+a^2}}} \tag{9}$$

**物理意义**：式(9)表明角速度并非常量，而是随半径减小而增大——越靠近中心，相同线速度对应更大的角速度。初始时刻 $\theta=0$ 时，$\frac{\mathrm{d}\theta}{\mathrm{d}t}\big|_{t=0} = \frac{1}{\sqrt{r_0^2+a^2}} \approx 0.1136$ rad/s。

### 2.3 螺线-刚性链耦合模型：后把手轨迹递推

**关键几何认知**：龙头前把手 $P_0$ 严格约束于螺线，但后续把手 $P_j$（$j \geq 1$）并不位于原螺线上，而是形成"自由轨迹"。这是由刚性连接约束与螺线几何曲率共同决定的本质特征。

已知第 $j-1$ 个把手位置 $P_{j-1} = (x_{j-1}, y_{j-1})$，第 $j$ 个把手 $P_j$ 满足：

**约束一（刚性杆长约束）**：两把手间距等于该节板凳的孔间距 $l_j$：

$$\boxed{|P_j - P_{j-1}| = l_j} \tag{10}$$

**约束二（切向近似约束）**：由于板凳龙整体沿螺线盘入，$P_j$ 应位于 $P_{j-1}$ 处螺线切线方向的"下游"区域。具体而言，$P_j$ 位于以 $P_{j-1}$ 为圆心、$l_j$ 为半径的圆上，且该圆与过 $P_{j-1}$ 的螺线切线存在两个交点，需选取沿盘入方向（顺时针、向心）的那个交点。

设螺线在 $P_{j-1}$ 处的单位切向量为 $\boldsymbol{\tau}_{j-1}$（顺时针方向），单位法向量为 $\boldsymbol{n}_{j-1}$（指向中心），则 $P_j$ 的近似位置可通过以下几何递推确定：

$$\boxed{P_j = P_{j-1} + l_j\left(\cos\alpha_j \cdot \boldsymbol{\tau}_{j-1} + \sin\alpha_j \cdot \boldsymbol{n}_{j-1}\right)} \tag{11}$$

其中 $\alpha_j$ 为杆件与螺线切线的夹角，需通过迭代求解满足全局一致性。

更精确的数值处理：将式(10)视为圆方程，与螺线"等距偏移"近似联立。定义 $P_j$ 的极角为 $\theta_j$，则其应满足：

$$\boxed{(x_j - x_{j-1})^2 + (y_j - y_{j-1})^2 = l_j^2} \tag{12}$$

其中 $x_j = r_j\cos\theta_j$，$y_j = r_j\sin\theta_j$，而 $r_j$ 并非简单等于 $r(\theta_j)$，需通过数值迭代求解。

**数值求解策略**：采用预测-校正迭代法。预测步：假设 $P_j$ 位于螺线上，即 $r_j^{(0)} = r(\theta_j^{(0)})$，由弧长近似估计 $\theta_j^{(0)}$；校正步：求解圆与修正轨迹的交点，迭代至满足距离约束。

### 2.4 相邻板凳夹角递推模型

为降低数值求解维度，引入相邻板凳夹角 $\phi_j$ 作为状态变量，建立几何不变量关系。

**定义**：$\phi_j$ 为第 $j$ 节板凳与第 $j+1$ 节板凳之间的夹角，即向量 $\overrightarrow{P_{j-1}P_j}$ 与 $\overrightarrow{P_jP_{j+1}}$ 的夹角。

设第 $j$ 节板凳的方向角为 $\psi_j$（与 $x$ 轴正向夹角），则：

$$\tan\psi_j = \frac{y_j - y_{j-1}}{x_j - x_{j-1}} \tag{13}$$

相邻板凳夹角：

$$\boxed{\phi_j = \psi_{j+1} - \psi_j} \tag{14}$$

**与螺线当地几何的关系**：在螺线上任一点，切线与径向的夹角 $\beta$ 满足：

$$\tan\beta = \frac{r}{|\mathrm{d}r/\mathrm{d}\theta|} = \frac{r}{a} = \frac{r_0-a\theta}{a} \tag{15}$$

对于紧密盘入的板凳龙，相邻板凳方向角之差 $\Delta\psi_j = \psi_j - \psi_{j-1}$ 应与螺线当地曲率相关。螺线曲率半径为：

$$\rho(\theta) = \frac{(r^2+a^2)^{3/2}}{r^2+2a^2} \tag{16}$$

局部近似下，孔间距 $l_j$ 对应的弧心角 $\Delta\theta_j \approx \frac{l_j}{\rho_{\text{eff}}}$，其中 $\rho_{\text{eff}}$ 为有效曲率半径。

**夹角递推方程**：考虑第 $j$ 节板凳后端（即 $P_j$）处，螺线切线方向为 $\psi_{\text{spiral}}(\theta_j)$，而实际板凳方向为 $\psi_j$。定义偏差角 $\delta_j = \psi_j - \psi_{\text{spiral}}(\theta_j)$，则在小偏差假设下：

$$\boxed{\phi_j \approx \frac{l_{j+1}}{\rho(\theta_{j+1})} - \frac{l_j}{\rho(\theta_j)} + (\delta_{j+1} - \delta_j)} \tag{17}$$

**物理意义**：式(17)表明夹角变化由两部分组成：螺线曲率变化导致的"几何强迫项"，以及前后板凳相对于螺线的偏差耦合。对于理想紧密盘入，$\delta_j \approx 0$，夹角完全由螺线几何决定。

### 2.5 无量纲分析与连续链近似

引入特征长度尺度 $L_{\text{typical}} = 2.20$ m（龙身孔间距），定义无量纲参数：

$$\boxed{\epsilon = \frac{a}{L_{\text{typical}}} = \frac{p}{2\pi L_{\text{typical}}} \approx \frac{0.55}{2\pi \times 2.20} \approx 0.0398 \approx 0.04} \tag{18}$$

**物理意义**：$\epsilon \ll 1$ 表征螺线相对于板凳尺度的"缓变"特征，是后续摄动分析的小参数。

定义无量纲变量：$\tilde{r} = r/L_{\text{typical}}$，$\tilde{s} = s/L_{\text{typical}}$，$\tilde{t} = v_h t/L_{\text{typical}}$，$\tilde{l}_j = l_j/L_{\text{typical}}$。龙头孔间距 $l_1 = 2.86$ m 对应 $\tilde{l}_1 \approx 1.30$，龙身 $\tilde{l}_j = 0.75$（$j \geq 2$）。

弧长微元的无量纲形式：

$$\mathrm{d}\tilde{s} = \sqrt{\tilde{r}^2 + \epsilon^2}\,\mathrm{d}\theta \tag{19}$$

**小 $\epsilon$ 渐近展开**：由于 $\epsilon \ll 1$，对根式进行展开：

$$\sqrt{\tilde{r}^2+\epsilon^2} = |\tilde{r}|\sqrt{1+\frac{\epsilon^2}{\tilde{r}^2}} = |\tilde{r}|\left(1 + \frac{\epsilon^2}{2\tilde{r}^2} - \frac{\epsilon^4}{8\tilde{r}^4} + O(\epsilon^6)\right) \tag{20}$$

零阶近似（$\epsilon \to 0$）：

$$\mathrm{d}\tilde{s}^{(0)} = |\tilde{r}|\,\mathrm{d}\theta = \tilde{r}\,\mathrm{d}\theta \quad (\tilde{r} > 0) \tag{21}$$

此即圆的弧长公式，对应螺线退化为同心圆的极限。

一阶修正：

$$\boxed{\mathrm{d}\tilde{s} = \tilde{r}\,\mathrm{d}\theta + \frac{\epsilon^2}{2\tilde{r}}\,\mathrm{d}\theta + O(\epsilon^4)} \tag{22}$$

**连续链近似**：当板凳节数足够多、单节尺度远小于曲率半径时，离散把手链可近似为连续曲线。设链的弧长参数为 $\sigma$（从龙头前把手沿链向后测量），则链上点的位置 $\boldsymbol{R}(\sigma, t)$ 满足：

$$\left|\frac{\partial\boldsymbol{R}}{\partial\sigma}\right| = 1 \tag{23}$$

链的整体运动受龙头牵引约束 $\boldsymbol{R}(0,t) = P_0(t)$ 及不可伸长约束。

在随时间演化的参考系中，链的形状由"滞后"于龙头的螺线段近似描述。具体而言，链上弧长参数 $\sigma$ 处的点，其运动状态近似等于龙头在 $\tau(t,\sigma)$ 时刻的状态，其中滞后时间由链长累积确定：

$$\boxed{\int_{t-\Delta t(\sigma)}^{t} v_h\,\mathrm{d}t' \approx \sigma \cdot \frac{L_{\text{chain}}}{L_{\text{spiral}}}} \tag{24}$$

更精确的连续模型：将链视为在螺线管道中运动的弹性杆，引入拉格朗日坐标。设物质坐标 $S \in [0, L_{\text{total}}]$ 表示从龙头开始的链长累积，则运动映射为：

$$\boldsymbol{R} = \boldsymbol{R}(S, t), \quad \left|\frac{\partial\boldsymbol{R}}{\partial S}\right| = 1 \tag{25}$$

动力学约束（忽略惯性，准静态假设）：

$$\frac{\partial\boldsymbol{R}}{\partial t}\bigg|_{S=0} = v_h\boldsymbol{\tau}_0(t), \quad \frac{\partial^2\boldsymbol{R}}{\partial S^2} = \kappa\boldsymbol{n} \tag{26}$$

其中 $\kappa$ 为链的曲

## 一、变量与参数定义

| 符号 | 类型 | 含义 | 单位/备注 |
|:---|:---|:---|:---|
| $N$ | 参数 | 板凳总节数 | $N = 223$ |
| $L_1$ | 参数 | 龙头板凳长度 | $3.41$ m |
| $L_i\,(i\geq 2)$ | 参数 | 龙身及龙尾板凳长度 | $2.20$ m |
| $W$ | 参数 | 板凳宽度 | $0.30$ m |
| $h$ | 参数 | 把手孔距板端距离 | $0.275$ m |
| $a$ | 参数 | 等距螺线极径增长系数 | $a = p/(2\pi)$，$p = 0.55$ m |
| $\theta_0$ | 参数 | 龙头初始极角 | $\theta_0 = 32\pi$ |
| $t$ | 变量 | 时间 | s |
| $\theta_1(t)$ | 变量 | 龙头前把手极角 | rad |
| $\theta_i(t)$ | 变量 | 第$i$节板凳前把手极角 | rad |
| $\mathbf{P}_i(t)$ | 变量 | 第$i$节板凳前把手位置 | $\mathbb{R}^2$ |
| $\mathbf{Q}_i(t)$ | 变量 | 第$i$节板凳后把手位置 | $\mathbb{R}^2$，且$\mathbf{Q}_i = \mathbf{P}_{i+1}$ |
| $\mathbf{M}_i(t)$ | 导出量 | 把手连线中点 | $\mathbb{R}^2$ |
| $\mathbf{C}_i(t)$ | 导出量 | 板凳几何中心 | $\mathbb{R}^2$ |
| $\hat{\mathbf{d}}_i(t)$ | 导出量 | 板凳中心轴单位方向向量 | $\mathbb{S}^1$ |
| $\hat{\mathbf{n}}_i(t)$ | 导出量 | 垂直于中心轴的单位向量 | $\mathbb{S}^1$ |
| $\mathbf{V}_{i,k}(t)$ | 导出量 | 第$i$节板凳第$k$个顶点 | $k=1,2,3,4$ |
| $\mathcal{R}_i(t)$ | 集合 | 第$i$节板凳占据的矩形区域 | $\mathbb{R}^2$的子集 |
| $t^*$ | 目标变量 | 盘入终止时刻（首次碰撞时刻） | s |
| $\mathcal{I}$ | 指标集 | 碰撞节对索引集 | $\{(i,j): |i-j| \geq 2\}$ |

---

## 二、核心数学模型

### 2.1 螺线簇几何约束与龙头运动学

龙头前把手沿等距螺线盘入，极坐标方程为：

$$r(\theta) = a\theta \tag{1}$$

其中螺距 $p = 0.55$ m，故 $a = p/(2\pi) = 0.55/(2\pi) \approx 0.0875$ m/rad。龙头前把手以恒定线速度 $v = 1$ m/s 沿螺线向内运动，即弧长随时间均匀增长：

$$\frac{ds}{dt} = v = 1 \tag{2}$$

弧长微元由极坐标弧长公式给出：

$$ds = \sqrt{r^2 + \left(\frac{dr}{d\theta}\right)^2}\,d\theta = a\sqrt{1+\theta^2}\,d\theta \tag{3}$$

由于龙头从 $\theta_0 = 32\pi$ 向内盘入，极角 $\theta$ 随时间单调递增（向中心运动对应 $\theta$ 增大），龙头极角 $\theta_1(t)$ 由隐式方程确定：

$$\int_{\theta_0}^{\theta_1(t)} a\sqrt{1+\xi^2}\,d\xi = t \tag{4}$$

该积分可解析求出：

$$\frac{a}{2}\left[\xi\sqrt{1+\xi^2} + \ln\left(\xi + \sqrt{1+\xi^2}\right)\right]_{\theta_0}^{\theta_1(t)} = t \tag{5}$$

**物理意义**：式(5)建立了龙头极角与时间的隐式关系。等距螺线的曲率半径 $\rho = a(1+\theta^2)^{3/2}/(2+\theta^2)$ 随 $\theta$ 增大而增大，但线速度恒定要求角速度 $\dot{\theta} = 1/[a\sqrt{1+\theta^2}]$ 随 $\theta$ 增大而衰减，呈现"越近中心、转角越急"的运动特征。

### 2.2 链式刚性约束与把手位置递推

第$i$节板凳的几何结构决定其前后把手间距（即有效杆长）：
- 龙头（$i=1$）：$l_1 = L_1 - 2h = 3.41 - 0.55 = 2.86$ m
- 龙身及龙尾（$i \geq 2$）：$l_i = L_i - 2h = 2.20 - 0.55 = 1.65$ m

相邻板凳通过把手铰接形成链式结构，满足刚性约束：

$$\|\mathbf{P}_i - \mathbf{Q}_i\| = l_i \tag{6}$$

其中 $\mathbf{Q}_i = \mathbf{P}_{i+1}$ 为第$i$节板凳后把手，即第$i+1$节板凳前把手。

**螺线方向与链式连接的几何关系分析**：对于盘入运动，龙头前把手位于半径 $r_1 = a\theta_1$ 处，后把手 $\mathbf{Q}_1$ 需同时满足：(a) 位于螺线 $r = a\theta$ 上；(b) 与 $\mathbf{P}_1$ 距离为 $l_1$。由于链式连接的方向性，后把手必须位于龙头"后方"，即沿螺线向中心方向。设后把手极角为 $\theta_2$，则其位置为 $\mathbf{P}_2 = (a\theta_2\cos\theta_2, a\theta_2\sin\theta_2)$，且 $\theta_2 > \theta_1$（向内盘入对应极角增大）。

该约束方程为：

$$(a\theta_2\cos\theta_2 - a\theta_1\cos\theta_1)^2 + (a\theta_2\sin\theta_2 - a\theta_1\sin\theta_1)^2 = l_1^2 \tag{7}$$

化简得：

$$a^2\left[\theta_1^2 + \theta_2^2 - 2\theta_1\theta_2\cos(\theta_2-\theta_1)\right] = l_1^2 \tag{8}$$

对于给定 $\theta_1$，需数值求解 $\theta_2 > \theta_1$。迭代递推可得全部把手极角 $\{\theta_i\}_{i=1}^{N+1}$，其中 $\theta_{N+1}$ 为龙尾后把手极角。

**单调性验证**：由式(8)，当 $\theta_2 - \theta_1 \to 0^+$ 时，左边 $\to a^2(\theta_2-\theta_1)^2 \to 0$；当 $\theta_2 - \theta_1 = \pi$ 时，左边 $= a^2(\theta_1+\theta_2)^2 > l_1^2$（典型情形）。由连续性，存在唯一解 $\theta_2 \in (\theta_1, \theta_1+\pi)$，保证 $\theta_i$ 严格单调递增，链式结构不自交。

### 2.3 板凳几何中心与顶点坐标

基于把手位置，定义第$i$节板凳的几何要素。把手连线中点：

$$\mathbf{M}_i = \frac{\mathbf{P}_i + \mathbf{Q}_i}{2} \tag{9}$$

中心轴单位方向向量（沿板凳长边，从后把手指向前把手）：

$$\hat{\mathbf{d}}_i = \frac{\mathbf{P}_i - \mathbf{Q}_i}{\|\mathbf{P}_i - \mathbf{Q}_i\|} = \frac{\mathbf{P}_i - \mathbf{P}_{i+1}}{l_i} \tag{10}$$

垂直于中心轴的单位向量（由 $\hat{\mathbf{d}}_i = (d_x, d_y)$ 得 $\hat{\mathbf{n}}_i = (-d_y, d_x)$）：

$$\hat{\mathbf{n}}_i = (-\hat{d}_{i,y}, \hat{d}_{i,x}) \tag{11}$$

**孔位设计与几何中心偏移**：板凳几何中心 $\mathbf{C}_i$ 与把手连线中点 $\mathbf{M}_i$ 存在系统性偏移。由于孔中心距板端为 $h = 0.275$ m，而板长为 $L_i$，故孔间距为 $L_i - 2h = l_i$，但板凳总长度 $L_i$ 超出把手连线的部分在两端各为 $h$。因此：

$$\mathbf{C}_i = \mathbf{M}_i + \left(\frac{L_i}{2} - h - \frac{l_i}{2}\right)\hat{\mathbf{d}}_i = \mathbf{M}_i \tag{12}$$

**巧合性说明**：恰好有 $L_i/2 - h = l_i/2$，即 $L_i - 2h = l_i$，故 $\mathbf{C}_i = \mathbf{M}_i$。该等式源于孔位对称设计：$h = 0.275$ m 恰好使孔中心位于"距板端 $27.5$ cm"处，而板长设计使得几何中心与把手连线中点重合。若参数变化，一般化中心偏移公式为：

$$\mathbf{C}_i = \mathbf{M}_i + \delta_i \hat{\mathbf{d}}_i, \quad \delta_i = \frac{L_i - l_i}{2} - h = \frac{L_i - (L_i-2h)}{2} - h = 0 \tag{13}$$

对于一般参数 $h', L_i'$，偏移量 $\delta_i' = (L_i' - l_i')/2 - h'$，其中 $l_i' = L_i' - 2h'$。

板凳四个顶点由中心、半长、半宽及方向向量确定：

$$\mathbf{V}_{i,k} = \mathbf{C}_i \pm \frac{L_i}{2}\hat{\mathbf{d}}_i \pm \frac{W}{2}\hat{\mathbf{n}}_i, \quad k=1,2,3,4 \tag{14}$$

具体地，设 $\mathbf{u}_i = \frac{L_i}{2}\hat{\mathbf{d}}_i$，$\mathbf{v}_i = \frac{W}{2}\hat{\mathbf{n}}_i$，则：

$$\begin{aligned}
\mathbf{V}_{i,1} &= \mathbf{C}_i + \mathbf{u}_i + \mathbf{v}_i, & \mathbf{V}_{i,2} &= \mathbf{C}_i + \mathbf{u}_i - \mathbf{v}_i \\
\mathbf{V}_{i,3} &= \mathbf{C}_i - \mathbf{u}_i - \mathbf{v}_i, & \mathbf{V}_{i,4} &= \mathbf{C}_i - \mathbf{u}_i + \mathbf{v}_i
\end{aligned} \tag{15}$$

第$i$节板凳占据的矩形区域为：

$$\mathcal{R}_i = \left\{\mathbf{C}_i + s\hat{\mathbf{d}}_i + t\hat{\mathbf{n}}_i : |s| \leq \frac{L_i}{2}, |t| \leq \frac{W}{2}\right\} \tag{16}$$

---

## 三、碰撞检测模型

### 3.1 碰撞判定准则

板凳龙碰撞定义为：存在非相邻两节板凳 $i, j$（满足 $|i-j| \geq 2$，相邻节通过把手铰接允许接触）其矩形区域发生内部交叠：

$$\mathcal{R}_i(t) \cap \mathcal{R}_j(t) \neq \emptyset, \quad \exists (i,j) \in \mathcal{I} \tag{17}$$

盘入终止时刻 $t^*$ 为首次满足式(17)的最小时间：

$$t^* = \inf\left\{t > 0 : \bigcup_{(i,j)\in\mathcal{I}} \mathbb{1}_{\mathcal{R}_i(t)\cap\mathcal{R}_j(t)\neq\emptyset} = 1\right\} \tag{18}$$

### 3.2 矩形-矩形相交检测算法

对于任意两节非相邻板凳 $\mathcal{R}_i$ 与 $\mathcal{R}_j$，采用分离轴定理（Separating Axis Theorem, SAT）进行精确碰撞检测。两凸多边形不相交当且仅当存在某条边的法线方向作为分离轴。

对于矩形，仅需检测四条潜在分离轴：$\hat{\mathbf{d}}_i, \hat{\mathbf{n}}_i, \hat{\mathbf{d}}_j, \hat{\mathbf{n}}_j$。定义投影算子 $\Pi_{\hat{\mathbf{a}}}(\mathcal{R}) = \{\mathbf{x}\cdot\hat{\mathbf{a}} : \mathbf{x}\in\mathcal{R}\}$，则相交判定为：

$$\mathcal{R}_i \cap \mathcal{R}_j \neq \emptyset \Leftrightarrow \forall \hat{\mathbf{a}} \in \{\hat{\mathbf{d}}_i, \hat{\mathbf{n}}_i, \hat{\mathbf{d}}_j, \hat{\mathbf{n}}_j\}: \Pi_{\hat{\mathbf{a}}}(\mathcal{R}_i) \cap \Pi_{\hat{\mathbf{a}}}(\mathcal{R}_j) \neq \emptyset \tag{19}$$

各投影区间为：
- $\Pi_{\hat{\mathbf{d}}_i}(\mathcal{R}_i) = [\mathbf{C}_i\cdot\hat{\mathbf{d}}_i - L_i/2, \mathbf{C}_i\cdot\hat{\mathbf{d}}_i + L_i/2]$
- $\Pi_{\hat{\mathbf{n}}_i}(\mathcal{R}_i) = [\mathbf{C}_i\cdot\hat{\mathbf{n}}_i - W/2, \mathbf{C}_i\cdot\hat{\mathbf{n}}_i + W/2]$

对 $\mathcal{R}_j$ 的投影需将顶点投影至各轴后取包络。

### 3.3 基于螺线结构的空间索引优化

**朴素算法的复杂度**：直接遍历所有 $\binom{N}{2} - (N-1) = O(N^2)$ 对非相邻板凳进行SAT检测，单次检测 $O(1)$，总复杂度 $O(N^2)$ 每时间步。对于 $N=223$ 及精细时间离散，计算负担显著。

**优化策略一：极角分桶索引**。利用螺线参数化结构，将板凳按前把手极角 $\theta_i$ 分桶。设桶宽度为 $\Delta\theta_{\text{bucket}}$，则第 $b$ 个桶包含满足 $b\cdot\Delta\theta_{\text{bucket}} \leq \theta_i < (b+1)\cdot\Delta\theta_{\text{bucket}}$ 的板凳。由于螺线盘入时板凳大致沿极角递增排列，仅当 $|\theta_i - \theta_j|$ 较小时才可能空间邻近。实际实现中，采用哈希表存储桶索引，将碰撞候选对从 $O(N^2)$ 降至 $O(N \cdot k_{\text{local}})$，其中 $k_{\text{local}}$ 为局部邻域平均板凳数。

**优化策略二：螺线圈层结构分析**。等距螺线的关键几何性质：相邻螺线圈的径向间距为常数：

$$\Delta r = r(\theta+2\pi) - r(\theta) = a(\theta+2\pi) - a\theta = 2\pi a = p = 0.55 \text{ m} \tag{20}$$

该间距与板凳宽度 $W = 0.30$ m 的比较具有重要物理意义：

$$\frac{\Delta r}{W} = \frac{0.55}{0.30} \approx 1.83 \tag{21}$$

即相邻螺线圈的径向间距约为板凳宽度的 $1.83$ 倍。这意味着：
- 同圈相邻板凳（沿螺线切向排列）因链式连接自然分离，不会碰撞；
- 相邻圈层（径向间隔 $\Delta r$）的板凳，其径向投影重叠需满足特定角条件，且 $1.83W > W$ 提供一定安全裕度；
- **碰撞必然发生在非相邻圈层**，即间隔 $k \geq 2$ 个螺距的圈层之间。

具体而言，第 $i$ 节板凳位于极角区间 $[\theta_i, \theta_{i+1}]$，对应半径区间 $[a\theta_i, a\theta_{i+1}]$。当板凳长度导致的角跨度 $\Delta\theta_i = \theta_{i+1} - \theta_i$ 满足 $a\Delta\theta_i \approx l_i$（小角度近似），对于龙身 $l_i = 1.65$ m，$\Delta\theta_i \approx 1.65/0.0875 \approx 18.9$ rad $\approx 3.0$ 圈。即单节板凳跨越约 $3$ 个螺距，其物理范围覆盖多个圈层。

**预判分析**：碰撞最可能发生于间隔 $m$ 圈的板凳之间，其中 $m$ 满足径向距离与板凳几何匹配。设两节板凳分别位于半径 $r, r'$ 处，径向间距 $|r-r'|$ 需小于板凳特征尺寸（长度或宽度）才可能碰撞。由 $\Delta r = 0.55$ m，$m$ 圈间隔的径向距为 $m \cdot 0.55$ m。与板凳宽度 $W=0.30$ m 比较：
- $m=1$：$0.55$ m，大于 $W$ 但小于 $L_i$，需特定角度

## 一、变量与参数定义

| 类别 | 符号 | 含义 | 单位 | 类型 |
|:---|:---|:---|:---|:---|
| **决策变量** | $p$ | 螺距（优化目标） | m | 连续变量 |
| **几何参数** | $D$ | 调头空间直径 | m | 常数（$D=9$） |
| | $R_{turn}$ | 调头空间半径，$R_{turn}=D/2$ | m | 导出常数 |
| | $L_0^{hole}$ | 龙头两把手间距 | m | 常数（$L_0^{hole}=2.86$） |
| | $L_i^{hole}\ (i\geq1)$ | 龙身/龙尾两把手间距 | m | 常数（$L_i^{hole}=1.65$） |
| | $L_0^{board}$ | 龙头板实际长度 | m | 常数（$L_0^{board}=3.41$） |
| | $L_i^{board}$ | 龙身/龙尾板实际长度 | m | 常数（$L_i^{board}=2.20$） |
| | $d_{overhang}$ | 孔中心到板端距离 | m | 常数（$d_{overhang}=0.275$） |
| | $w$ | 板凳宽度 | m | 常数（$w=0.30$） |
| **螺线参数** | $r_0$ | 螺线初始半径 | m | 导出常数 |
| | $\theta$ | 极角（广义坐标） | rad | 连续变量 |
| | $r(\theta;p)$ | 极径，螺距$p$的函数 | m | 状态函数 |
| **运动学变量** | $\theta_0(t)$ | 龙头前把手极角 | rad | 时间函数 |
| | $\dot{\theta}_0(t)$ | 龙头前把手角速度 | rad/s | 时间函数（负值表示盘入） |
| | $\mathbf{r}_i^{(f)}(t)$ | 第$i$节板凳前把手位置向量 | m | 二维向量 |
| | $\mathbf{r}_i^{(b)}(t)$ | 第$i$节板凳后把手位置向量 | m | 二维向量 |
| | $\phi_i(t)$ | 第$i$节板凳方位角（长边方向） | rad | 时间函数 |
| **约束相关** | $t_{col}(p)$ | 首次碰撞时刻 | s | 隐函数 |
| | $t_{bound}(p)$ | 龙头到达边界时刻 | s | 隐函数 |
| | $t_{term}(p)$ | 实际终止时刻 | s | 导出变量 |
| **集合** | $\mathcal{B}_i$ | 第$i$节板凳占据的平面点集 | — | 几何集合 |
| | $\mathcal{D}_{turn}$ | 调头空间区域 | — | 圆形区域 |

---

## 二、核心数学模型

### 2.1 等距螺线的参数化族与盘入方向约定

等距螺线（阿基米德螺线）在盘入问题中采用半径随角度增加而减小的参数化形式。设盘入方向为极角$\theta$增加而极径$r$减小的方向，则螺线方程为：

$$\boxed{r(\theta; p) = r_0 - \frac{p}{2\pi}\theta = r_0 - b(p)\cdot\theta} \tag{1}$$

其中 $b(p) = p/(2\pi)$ 为螺线收缩率，$r_0$ 为初始半径。对应的直角坐标参数方程为：

$$\boxed{\mathbf{r}(\theta; p) = \left(\left[r_0 - b(p)\theta\right]\cos\theta,\; \left[r_0 - b(p)\theta\right]\sin\theta\right)} \tag{2}$$

**盘入方向与角速度符号约定**：由于盘入过程要求龙头从外圈向中心运动，极径随时间递减，故$\dot{\theta}_0(t) < 0$。定义角速度大小为$\omega_0 = |\dot{\theta}_0| = -\dot{\theta}_0 > 0$，则龙头前把手以恒定线速度$v_0$运动时满足弧长约束：

$$\boxed{\dot{\theta}_0(t) = -\frac{v_0}{\sqrt{r^2(\theta_0;p) + \left(\frac{dr}{d\theta}\right)^2}} = -\frac{v_0}{b(p)\sqrt{\left(\frac{r_0 - b\theta_0}{b}\right)^2 + 1}} = -\frac{v_0}{\sqrt{(r_0-b\theta_0)^2 + b^2}} \tag{3}$$

**初始条件与调头空间的关系**：若龙头从第$N_0$圈开始盘入，则初始半径$r_0 = N_0 p$。调头空间半径$R_{turn} = 4.5$ m 构成螺线终止的硬约束，要求存在$\theta_{turn}$使得$r(\theta_{turn}; p) = R_{turn}$，即：

$$N_0 p - \frac{p}{2\pi}\theta_{turn} = R_{turn} \implies \theta_{turn} = 2\pi\left(N_0 - \frac{R_{turn}}{p}\right) \tag{4}$$

为保证$\theta_{turn} > 0$，需$N_0 > R_{turn}/p$。若取$N_0 = 16$，则对任意$p > R_{turn}/16 \approx 0.281$ m，龙头可在到达调头空间边界前完成盘入。

**物理意义**：式(1)-(3)建立了盘入运动的完整参数化描述。负号约定确保$\theta$增加对应半径减小，符合"盘入"的物理直觉；分母中的几何因子反映了阿基米德螺线弧长微元$ds = \sqrt{r^2 + (dr/d\theta)^2}\,d\theta$的非欧特性。

---

### 2.2 链式刚体系统的运动学约束

板凳龙由223节板凳通过把手铰接形成链式结构。第$i$节板凳的几何由其前后把手位置$\mathbf{r}_i^{(f)}(t)$和$\mathbf{r}_i^{(b)}(t)$完全确定，满足以下约束：

**等距螺线约束**（所有把手位于同一条螺线上）：
$$\boxed{|\mathbf{r}_i^{(f)}(t)| = r_0 - b(p)\cdot\theta_i^{(f)}(t), \quad \theta_i^{(f)}(t) = \arg(\mathbf{r}_i^{(f)}(t))} \tag{5}$$

$$\boxed{|\mathbf{r}_i^{(b)}(t)| = r_0 - b(p)\cdot\theta_i^{(b)}(t), \quad \theta_i^{(b)}(t) = \arg(\mathbf{r}_i^{(b)}(t))} \tag{6}$$

**把手间距约束**（相邻孔中心距离固定）：
$$\boxed{|\mathbf{r}_i^{(b)}(t) - \mathbf{r}_i^{(f)}(t)| = L_i^{hole}} \tag{7}$$

**铰接约束**（相邻板凳共享把手）：
$$\boxed{\mathbf{r}_i^{(b)}(t) = \mathbf{r}_{i+1}^{(f)}(t), \quad i = 0, 1, \ldots, 221} \tag{8}$$

其中有效把手间距为：
$$L_i^{hole} = \begin{cases} 2.86\,\text{m}, & i=0 \text{（龙头）} \\ 1.65\,\text{m}, & i \geq 1 \text{（龙身/龙尾）} \end{cases}$$

**板凳方位角与几何重构**：第$i$节板凳的长边方向（方位角）由前后把手确定：
$$\boxed{\phi_i(t) = \arg\left(\mathbf{r}_i^{(b)}(t) - \mathbf{r}_i^{(f)}(t)\right)} \tag{9}$$

板凳中心线为其长边中线，中心点位置为：
$$\mathbf{c}_i(t) = \frac{\mathbf{r}_i^{(f)}(t) + \mathbf{r}_i^{(b)}(t)}{2} \tag{10}$$

**关键区分——把手间距与板实际长度**：把手间距$L_i^{hole}$仅连接两孔中心，而板凳实际长度$L_i^{board}$包含两端悬伸：
$$L_i^{board} = L_i^{hole} + 2d_{overhang} = L_i^{hole} + 0.55\,\text{m} \tag{11}$$

这一区分对碰撞检测至关重要：板凳两端各延伸$d_{overhang} = 0.275$ m 的实体板面，在密集盘绕时成为碰撞的首要风险区域。

---

### 2.3 板凳占据区域的精确几何描述

为进行严格的碰撞检测，需建立每节板凳作为刚体占据的平面点集$\mathcal{B}_i$。以第$i$节板凳中心点$\mathbf{c}_i$为参考，沿中心线方向$\mathbf{e}_\parallel = (\cos\phi_i, \sin\phi_i)$和垂直方向$\mathbf{e}_\perp = (-\sin\phi_i, \cos\phi_i)$建立局部坐标系，则：

$$\boxed{\mathcal{B}_i(t) = \left\{\mathbf{x} \in \mathbb{R}^2 : \left|(\mathbf{x}-\mathbf{c}_i)\cdot\mathbf{e}_\parallel\right| \leq \frac{L_i^{board}}{2},\; \left|(\mathbf{x}-\mathbf{c}_i)\cdot\mathbf{e}_\perp\right| \leq \frac{w}{2}\right\}} \tag{12}$$

即$\mathcal{B}_i$为以$\mathbf{c}_i$为中心、长$L_i^{board}$、宽$w$、方位角$\phi_i$的矩形区域。

**碰撞判定**：两节板凳$i$与$j$（$|i-j| \geq 2$，非相邻）发生碰撞当且仅当：
$$\boxed{\mathcal{B}_i(t) \cap \mathcal{B}_j(t) \neq \emptyset} \tag{13}$$

相邻板凳（$|i-j|=1$）因铰接约束天然相交于把手点，不构成碰撞。

---

### 2.4 渐近分析：阿基米德螺线的局部圆弧近似与最小间距下界

当$\theta \gg 1$（即远离中心的多圈情形），阿基米德螺线呈现重要的渐近特性。对螺线$r(\theta) = r_0 - b\theta$，考察局部曲率与相邻圈间距：

**局部曲率计算**：螺线的曲率半径为
$$\rho(\theta) = \frac{\left[r^2 + (dr/d\theta)^2\right]^{3/2}}{\left|r^2 + 2(dr/d\theta)^2 - r(d^2r/d\theta^2)\right|} = \frac{\left[(r_0-b\theta)^2 + b^2\right]^{3/2}}{(r_0-b\theta)^2 + 2b^2} \tag{14}$$

当$r \gg b$（即$r \gg p/2\pi$）时，近似有：
$$\rho(\theta) \approx r_0 - b\theta = r(\theta) \tag{15}$$

此时螺线局部近似为半径$r(\theta)$的圆弧。

**相邻圈最小间距的显式下界**：考虑极角相差$2\pi$的两点，即第$k$圈与第$k+1$圈上极角相同的径向对应点。设第$k$圈半径为$r_k = r_0 - 2\pi b k = r_0 - kp$，则第$k+1$圈对应半径为$r_{k+1} = r_k - p$。径向间距恰为螺距$p$。

然而，由于板凳沿切向排列而非径向，实际需考察沿板凳法向的最小间距。设某节板凳位于半径$r$处，其长边沿切向，宽度$w$沿法向跨越区间$[r-w/2, r+w/2]$。相邻内圈板凳的中心线位于$r-p$处，其宽度覆盖$[r-p-w/2, r-p+w/2]$。

两圈板凳不发生径向重叠的充分条件为：
$$r - \frac{w}{2} > r - p + \frac{w}{2} \implies p > w \tag{16}$$

此即螺距必须大于板凳宽度的基本约束。但该条件过于宽松，未考虑板凳的实际长度和切向偏移。

**更精细的间距分析**：考虑沿螺线相距半圈（$\Delta\theta = \pi$）的两节板凳，其切向距离约为$\pi r$，径向差约为$p/2$。当螺线局部近似为圆弧时，这两节板凳的相对位置形成"错列"构型。设一节板凳中心在$(r, 0)$，另一节在近似坐标$(r-p/2, \pi r)$（展开为直角近似），则实际欧氏距离为：
$$d^2 \approx \left(\frac{p}{2}\right)^2 + (\pi r)^2 \approx (\pi r)^2 \quad (\text{当 } r \gg p) \tag{17}$$

此距离远大于板凳尺寸，故远距离板凳无碰撞风险。碰撞仅可能发生在相邻圈（$\Delta\theta \approx 2\pi$）且切向接近的位置。

对于相邻圈切向接近的情形（$\Delta\theta = 2\pi + \delta$，$|\delta| \ll 1$），两节板凳中心径向差为$p$，切向弧长差为$r\delta$。当$|r\delta| < L_i^{board}$时，两板凳在切向投影上重叠，构成潜在碰撞。此时最小间距要求：
$$\sqrt{p^2 + (r\delta)^2} > L_i^{board}\cos\alpha + w\sin\alpha \tag{18}$$

其中$\alpha$为两板凳中心连线与径向的夹角，$\tan\alpha = r\delta/p$。最坏情形为$\delta \to 0$（纯径向对齐），此时要求$p > L_i^{board}$，但这与密集盘绕目标矛盾。实际上，由于链式约束，相邻圈板凳存在固有切向偏移，使得$\delta$有非零下界。

---

### 2.5 平行曲线理论：板凳中心线与边界偏移的解析约束

板凳的实体边界由其中心线沿法向偏移产生，这自然引入**平行曲线（offset curve）**概念。对平面曲线$\Gamma: \mathbf{r}(s)$（$s$为弧长参数），其距离为$d$的平行曲线为：
$$\Gamma_d: \mathbf{r}_d(s) = \mathbf{r}(s) + d\cdot\mathbf{n}(s) \tag{19}$$

其中$\mathbf{n}(s)$为单位法向量。平行曲线的曲率与原曲线曲率$\kappa$满足：
$$\kappa_d = \frac{\kappa}{1 + d\kappa} \quad (\text{对 } d\kappa > -1) \tag{20}$$

**板凳内外边界的平行曲线描述**：第$i$节板凳中心线为连接前后把手的线段，可嵌入局部螺线切线近似。板凳内侧边界（靠近螺线中心一侧）为中心线沿$-\mathbf{n}$方向偏移$w/2$，外侧边界为沿$+\mathbf{n}$方向偏移$w/2$。

对阿基米德螺线$r = r_0 - b\theta$，其单位切向量和法向量为：
$$\mathbf{T} = \frac{(-b\cos\theta - r\sin\theta, -b\sin\theta + r\cos\theta)}{\sqrt{r^2+b^2}}, \quad \mathbf{n} = \mathbf{T}^\perp \tag{21}$$

螺线曲率为：
$$\kappa(\theta) = \frac{r^2 + 2b^2}{(r^2+b^2)^{3/2}} \approx \frac{1}{r}\left(1 + \frac{3b^2}{2r^2}\right) \quad (r \gg b) \tag{22}$$

**螺距-宽度-曲率的解析约束**：板凳宽度$w$沿法向跨越，其内侧边界更靠近曲率中心，外侧边界更远。对凸曲线（$\kappa > 0$），内侧平行曲线收缩，外侧扩张。当曲率过大时，内侧平行曲线可能出现奇点（$w\kappa/2 \to 1$），对应"过度弯曲"导致的几何自交。

对阿基米德螺线，最大曲率在中心附近（$r \to R_{turn}$）：
$$\kappa_{max} \approx \frac{1}{R_{turn}} = \frac{2}{9}\,\text{m}^{-1} \approx 0.222\,\text{m}^{-1} \tag{23}$$

内侧平行曲线无奇点的条件：
$$\frac{w}{2}\kappa_{max} < 1 \implies w < \frac{2}{\kappa_{max}} = 2R_{turn} = 9\,\text{m} \tag{24}$$

该条件宽松满足（$w = 0.3$ m），但揭示了曲率与宽度的基本制约。

**相邻圈平行曲线的间距约束**：考虑螺线中心线与其相邻内圈（径向距离$p$）的平行曲线关系。内圈中心线相当于外圈中心线的"负偏移"曲线（偏移$-p$沿径向，非严格法向）。两圈板凳的实体区域分别为各自中心线的$\pm w/2$法向偏移带。

设外圈中心线曲率半径为$\rho = 1/\kappa$，则内圈中心线近似曲率半径为$\rho - p$（对同心圆严格成立，对螺线为一阶近似）。外圈内侧边界到内圈外侧边界的净间距为：
$$\Delta_{net} = p - w - \Delta_{curvature} \tag{25}$$

其中$\Delta_{curvature}$为曲率引起的"侵占"修正

## 一、变量与参数定义

| 类别 | 符号 | 名称 | 单位 | 说明 |
|:---|:---|:---|:---|:---|
| **几何参数** | $R$ | 圆弧半径 | m | 两段圆弧的公共半径（对称情形） |
| | $R_1, R_2$ | 第一、二段圆弧半径 | m | 非对称双圆弧情形 |
| | $\alpha_1, \alpha_2$ | 第一、二段圆弧圆心角 | rad | 圆弧对应的中心角 |
| | $L_S$ | S形曲线总弧长 | m | 调头路径总长度 |
| | $s$ | 弧长参数 | m | 沿曲线的自然参数，$s \in [0, L_S]$ |
| | $w$ | 板凳宽度 | m | $w = 0.30$，垂直于龙身方向 |
| | $l_i$ | 第$i$节板凳有效长度 | m | 两孔中心间距，龙头$l_1=2.86$，龙身/龙尾$l_i=1.65$ $(i\geq 2)$ |
| **坐标与位置** | $O_1, O_2$ | 第一、二段圆弧圆心 | — | 二维平面上的点 |
| | $A$ | 起点（盘入交点） | — | 螺线与调头空间边界交点 |
| | $B$ | 终点（盘出交点） | — | 螺线与调头空间边界交点 |
| | $T$ | 两段圆弧切点 | — | S形曲线的拐点（曲率变号点） |
| | $\mathbf{r}(s)$ | 位置向量 | m | 曲线参数方程 |
| | $\mathbf{r}_i$ | 第$i$个把手位置 | m | 链式结构节点坐标 |
| **运动学参数** | $v$ | 龙头前把手速度 | m/s | 恒定值，$v = 1$ |
| | $\mathbf{v}_i$ | 第$i$个把手速度向量 | m/s | 二维速度 |
| | $\omega_i$ | 第$i$节板凳角速度 | rad/s | 绕后把手的转动角速度 |
| | $a_n$ | 法向加速度（向心加速度） | m/s² | $a_n = v^2/\rho$ |
| | $a_t$ | 切向加速度 | m/s² | 速度大小变化率，此处$a_t = 0$ |
| | $j$ | 加加速度（jerk） | m/s³ | 加速度变化率，$j = \mathrm{d}a/\mathrm{d}t$ |
| | $a_{\max}$ | 最大允许向心加速度 | m/s² | 运动学约束上限 |
| | $j_{\max}$ | 最大允许jerk | m/s³ | 舒适性约束上限 |
| **螺线参数** | $p$ | 螺距 | m | 等距螺线的径向间距 |
| | $r_0$ | 调头空间半径 | m | 圆形调头区域边界半径 |
| | $\theta$ | 极角 | rad | 螺线参数角，逆时针为正 |
| | $b = p/(2\pi)$ | 螺线增长率 | m/rad | 阿基米德螺线参数 |
| **连续性参数** | $\kappa$ | 曲率 | m⁻¹ | $\kappa = 1/\rho$，带符号（逆时针为正） |
| | $\kappa'$ | 曲率对弧长的导数 | m⁻² | G²连续性指标 |
| | $\kappa''$ | 曲率对弧长的二阶导 | m⁻³ | G³连续性指标 |
| | $\tau$ | 切向量与x轴夹角 | rad | 曲线切向角 |

---

## 二、核心数学模型

### 2.1 调头空间与螺线方程

建立平面直角坐标系：原点$O$为盘入螺线中心，$x$轴正向水平向右，$y$轴正向竖直向上。盘入螺线为顺时针向内收缩的阿基米德螺线，其极坐标方程为：

$$\boxed{r(\theta) = r_0 - b\theta, \quad \theta \in \left[0, \frac{r_0}{b}\right]} \tag{1}$$

其中$b = p/(2\pi)$为螺线增长率，$r_0$为调头空间边界半径。当$\theta = 0$时，$r = r_0$位于外圈；随着$\theta$增大，螺线顺时针向内盘入，最终趋于中心。

盘出螺线需与盘入螺线实现中心对称变换，使得舞龙队调头后沿相反方向盘出。采用严格的中心对称映射$(r, \theta) \mapsto (r, \theta + \pi)$，即盘出螺线方程为：

$$\boxed{r(\theta) = r_0 + b\theta, \quad \theta \geq 0} \tag{2}$$

或等价地，以盘入参数表示：$r(\theta) = r_0 - b(\theta - \pi)$，其中$\theta \in [\pi, \pi + r_0/b]$。该变换保证盘入螺线上点$(r, \theta)$与盘出螺线上点$(r, \theta+\pi)$关于原点对称，形成完整的S形调头结构。

调头空间为以原点$O$为中心、半径$r_0$的圆域：

$$\boxed{\mathcal{D} = \left\{(x,y) \in \mathbb{R}^2 : x^2 + y^2 \leq r_0^2\right\}} \tag{3}$$

起点$A$（盘入交点）和终点$B$（盘出交点）位于调头空间边界$\partial\mathcal{D}$上，满足：

$$\boxed{|\mathbf{r}_A| = |\mathbf{r}_B| = r_0} \tag{4}$$

且由中心对称性，$\mathbf{r}_B = -\mathbf{r}_A$。

**方向标注说明**：在图1所示坐标系中，盘入螺线沿顺时针方向（$\theta$增大时切向角减小）由外向内收缩；盘出螺线沿逆时针方向（$\theta$增大时切向角增大）由内向外扩展。两螺线在调头空间边界处切向相反，需通过S形曲线实现平滑过渡。

---

### 2.2 S形双圆弧曲线的几何构造与连续性分析

#### 2.2.1 对称双圆弧结构

采用对称双圆弧结构，设两段圆弧半径相等$R_1 = R_2 = R$，圆心角相等$\alpha_1 = \alpha_2 = \alpha$。建立几何约束方程组：

**位置约束**（圆弧过给定点）：
$$\boxed{|\mathbf{r}_A - \mathbf{O}_1| = R, \quad |\mathbf{T} - \mathbf{O}_1| = R} \tag{5}$$

$$\boxed{|\mathbf{T} - \mathbf{O}_2| = R, \quad |\mathbf{r}_B - \mathbf{O}_2| = R} \tag{6}$$

**切向约束**（G¹连续条件）：
$$\boxed{\left.\frac{\mathrm{d}\mathbf{r}}{\mathrm{d}s}\right|_{s=L_1^-} = \left.\frac{\mathrm{d}\mathbf{r}}{\mathrm{d}s}\right|_{s=L_1^+}} \tag{7}$$

其中$L_1 = R\alpha$为第一段圆弧弧长。

**曲率分析**：第一段圆弧曲率$\kappa_1 = +1/R$（逆时针转向，取正），第二段圆弧曲率$\kappa_2 = -1/R$（顺时针转向，取负）。在切点$T$处：

$$\boxed{\lim_{s \to L_1^-} \kappa(s) = +\frac{1}{R} \neq -\frac{1}{R} = \lim_{s \to L_1^+} \kappa(s)} \tag{8}$$

故曲率在$T$点发生**符号跳变**，S形双圆弧仅能实现**G¹几何连续**（切向连续），**不满足G²连续**（曲率连续）。

#### 2.2.2 曲率不连续的物理影响：Jerk约束分析

设龙头以恒定速率$v = 1$ m/s沿曲线运动。法向加速度$a_n = \kappa v^2$在切点$T$处的跃变为：

$$\boxed{\Delta a_n = a_n(L_1^+) - a_n(L_1^-) = -\frac{v^2}{R} - \frac{v^2}{R} = -\frac{2v^2}{R}} \tag{9}$$

跃变幅度$|\Delta a_n| = 2v^2/R$。由于速度大小恒定，切向加速度$a_t = 0$，总加速度跃变完全由法向分量贡献。

加加速度（jerk）定义为加速度对时间的导数。在切点$T$处，由于加速度发生有限跃变，理想化模型中jerk为Dirac delta函数（无穷大脉冲）。实际物理系统中，把手连接存在柔性，跃变在有限时间$\Delta t$内完成，等效jerk为：

$$\boxed{j_{\text{eff}} = \frac{|\Delta a_n|}{\Delta t} = \frac{2v^2}{R \cdot \Delta t}} \tag{10}$$

为保证舞龙队运动平稳性及表演者舒适性，需施加jerk约束：

$$\boxed{j_{\text{eff}} \leq j_{\max} \implies R \geq \frac{2v^2}{j_{\max} \cdot \Delta t}} \tag{11}$$

典型取值：若$j_{\max} = 5$ m/s³（人体舒适阈值），$\Delta t = 0.1$ s（柔性连接等效时间），则$R \geq 4$ m。该约束与向心加速度约束$a_n = v^2/R \leq a_{\max}$共同决定最小允许半径。

#### 2.2.3 对称双圆弧的显式解

设起点$A$位于$(r_0, 0)$，终点$B$位于$(-r_0, 0)$（由中心对称性）。两段圆弧在切点$T$处相切，且$T$位于$y$轴上。由几何对称性，$T = (0, y_T)$，两段圆弧圆心位于$x$轴上：$O_1 = (x_1, 0)$，$O_2 = (x_2, 0)$。

由$|O_1A| = |O_1T| = R$：
$$(x_1 - r_0)^2 = x_1^2 + y_T^2 = R^2$$

由$|O_2B| = |O_2T| = R$：
$$(x_2 + r_0)^2 = x_2^2 + y_T^2 = R^2$$

解得：$x_1 = (r_0^2 - y_T^2)/(2r_0)$，$x_2 = -(r_0^2 - y_T^2)/(2r_0) = -x_1$。

由$R^2 = x_1^2 + y_T^2$，代入得：

$$\boxed{R = \frac{r_0^2 + y_T^2}{2r_0}, \quad \alpha = 2\arctan\left(\frac{y_T}{r_0}\right)} \tag{12}$$

总弧长：

$$\boxed{L_S = 2R\alpha = \frac{r_0^2 + y_T^2}{r_0} \arctan\left(\frac{y_T}{r_0}\right)} \tag{13}$$

参数$y_T \in (0, r_0)$控制S形曲线的"扁平度"：$y_T \to 0$时曲线退化为直径，$y_T \to r_0$时曲线趋于半圆。

---

### 2.3 链式结构运动学模型

#### 2.3.1 速度递推的二维向量形式

将223节板凳的把手视为链式节点$\mathbf{r}_0, \mathbf{r}_1, \ldots, \mathbf{r}_{223}$，其中$\mathbf{r}_0$为龙头前把手，$\mathbf{r}_i$ $(i \geq 1)$为第$i$节板凳后把手（即第$i+1$节板凳前把手）。

第$i$节板凳的刚体约束：长度固定$|\mathbf{r}_i - \mathbf{r}_{i-1}| = l_i$，其中$l_1 = 2.86$ m，$l_i = 1.65$ m $(i \geq 2)$。

对约束求导得速度关系。设第$i$节板凳角速度为$\omega_i$（逆时针为正），则后把手速度为：

$$\boxed{\mathbf{v}_i = \mathbf{v}_{i-1} + \omega_i \begin{pmatrix} 0 & -1 \\ 1 & 0 \end{pmatrix} (\mathbf{r}_i - \mathbf{r}_{i-1})} \tag{14}$$

该式表明：后把手速度等于前把手速度加上绕前把手的转动速度，转动速度方向垂直于板凳轴向，大小为$\omega_i l_i$。

#### 2.3.2 角速度与链式约束的关系

由刚体约束$|\mathbf{r}_i - \mathbf{r}_{i-1}|^2 = l_i^2$对时间求导：

$$(\mathbf{r}_i - \mathbf{r}_{i-1}) \cdot (\mathbf{v}_i - \mathbf{v}_{i-1}) = 0$$

将式(14)代入，利用$(\mathbf{r}_i - \mathbf{r}_{i-1}) \perp \begin{pmatrix} 0 & -1 \\ 1 & 0 \end{pmatrix}(\mathbf{r}_i - \mathbf{r}_{i-1})$，自动满足。故角速度$\omega_i$不能由单节约束确定，需由相邻两节板凳的耦合关系或边界条件确定。

对式(14)求模并考虑$|\mathbf{v}_0| = v$（龙头速度恒定），引入板凳轴向单位向量$\mathbf{e}_i = (\mathbf{r}_i - \mathbf{r}_{i-1})/l_i$及其法向$\mathbf{e}_i^\perp = \begin{pmatrix} 0 & -1 \\ 1 & 0 \end{pmatrix}\mathbf{e}_i$，可将速度分解为：

$$\mathbf{v}_i = v_{i,\parallel}\mathbf{e}_i + v_{i,\perp}\mathbf{e}_i^\perp$$

其中$v_{i,\perp} = \omega_i l_i$。由链式传递，第$i$节板凳前把手速度$\mathbf{v}_{i-1}$的轴向分量决定该节板凳的"牵引"效应。

对于等螺距螺线轨道上的稳态运动，各节板凳角速度满足递推：

$$\boxed{\omega_i = \frac{v_{i-1} \sin(\beta_{i-1} - \tau_{i-1})}{l_i}} \tag{15}$$

其中$\beta_{i-1}$为速度方向角，$\tau_{i-1}$为板凳轴向角，二者差异源于轨道曲率。

---

### 2.4 矩形扫掠体碰撞模型

#### 2.4.1 单节板凳的矩形表示

第$i$节板凳为长$l_i$、宽$w = 0.30$ m的矩形，其四个顶点由中心位置、轴向角及几何偏移确定。设第$i$节板凳中心（两孔中心中点）为：

$$\mathbf{c}_i = \mathbf{r}_{i-1} + \frac{l_i}{2}\mathbf{e}_i$$

则四个顶点为：

$$\mathbf{c}_i \pm \frac{l_i}{2}\mathbf{e}_i \pm \frac{w}{2}\mathbf{e}_i^\perp$$

#### 2.4.2 相邻板凳转角约束

相邻两节板凳$i$与$i+1$的夹角为：

$$\Delta\theta_i = \arccos(\mathbf{e}_i \cdot \mathbf{e}_{i+1}) \in [0, \pi]$$

当$\Delta\theta_i$过大时，相邻矩形发生干涉。建立最小间距模型：设两矩形最近顶点距离为$d_{\min}$，安全阈值$d_{\text{safe}} > 0$。

对于铰接矩形链，临界碰撞情形为：前一节板凳后端角点与后一节板凳前端角点接触。由余弦定理，两后端孔（间距$l_i$）与两前端孔（间距$l_{i+1}$）构成的四边形中，对角线约束导出：

$$\boxed{|\Delta\theta_i| \leq \arccos\left(1 - \frac{d_{\min}^2}{2l_i l_{i+1}}\right)} \tag{16}$$

当$l_i = l_{i+1} = l$时简化为：

$$\boxed{|\Delta\theta_i| \leq 2\arcsin\left(\frac{d_{\min}}{2l}\right) \approx \frac{d_{\min}}{l} \quad (\text{小角度近似})} \tag{17}$$

对于龙身段$l = 1.65$ m，取$d_{\min} = 0.05$ m（5 cm安全间隙），得$|\Delta\theta_i| \leq 0.0303$ rad $\approx 1.74°$；对于龙头段$l_1 = 2.86$ m，同条件下$|\Delta\theta_1| \leq 0.0175$ rad $\approx 1.00°$。

**全局碰撞约束**：调头过程中，需保证所有相邻节段满足式(16)，且非相邻节段（尤其是盘入与盘出螺线的近圈部分）满足分离约束。该约束显著限制了S形双圆弧的最小曲率半径选择。

---

### 2.5 高阶曲线构造：Clothoid（回旋曲线）段

为克服S形双圆弧的G²不连续缺陷，引入Clothoid（欧拉螺旋线）段作为过渡，构造G²连续的调头曲线。

#### 2

## 一、变量与参数定义

| 类别 | 符号 | 含义 | 单位 | 取值/范围 |
|:---|:---|:---|:---|:---|
| **索引变量** | $i$ | 板凳编号 | — | $i = 1, 2, \ldots, N$，其中$N=223$ |
| | $j$ | 把手点编号 | — | $j = 1, 2, \ldots, N+1$ |
| **几何参数** | $L_1$ | 龙头板凳孔间距 | m | 2.86 |
| | $L_i\ (i\geq 2)$ | 龙身/龙尾板凳孔间距 | m | 1.65 |
| | $w$ | 板凳宽度 | m | 0.30 |
| **全局状态变量** | $\mathbf{r}_j = (x_j, y_j)^{\mathsf{T}}$ | 第$j$个把手位置 | m | 二维平面坐标 |
| | $\mathbf{v}_j = (v_{jx}, v_{jy})^{\mathsf{T}}$ | 第$j$个把手速度 | m/s | 待求量，共$2(N+1)$个分量 |
| | $v_j = \|\mathbf{v}_j\|$ | 第$j$个把手速度幅值 | m/s | $v_j \geq 0$ |
| **方向与标架** | $\phi_i$ | 第$i$节板凳长轴方向角 | rad | $\phi_i = \arctan\frac{y_{i+1}-y_i}{x_{i+1}-x_i}$ |
| | $\mathbf{e}_i = (\cos\phi_i, \sin\phi_i)^{\mathsf{T}}$ | 板凳长轴单位向量 | — | 由全局坐标直接确定 |
| | $\mathbf{n}_i = (-\sin\phi_i, \cos\phi_i)^{\mathsf{T}}$ | 板凳法向单位向量 | — | $\mathbf{n}_i = \mathbf{e}_i^{\perp}$ |
| | $\mathbf{R}(\phi_i) = \begin{bmatrix} \cos\phi_i & -\sin\phi_i \\ \sin\phi_i & \cos\phi_i \end{bmatrix}$ | 局部到全局的旋转变换矩阵 | — | 正交矩阵，$\mathbf{R}^{\mathsf{T}}\mathbf{R} = \mathbf{I}$ |
| **局部标架分量** | $\tilde{\mathbf{v}}_i^{(k)} = (v_{i,\parallel}^{(k)}, v_{i,\perp}^{(k)})^{\mathsf{T}}$ | 第$k$节板凳局部标架中第$i$个把手的速度 | m/s | 上标$(k)$标明所属标架 |
| **角速度** | $\omega_i$ | 第$i$节板凳绕其前把手（第$i$个把手）的角速度 | rad/s | 垂直于平面的伪标量 |
| **优化变量** | $v_1^{\max}$ | 龙头最大允许速度 | m/s | **优化目标** |
| | $\mathbf{V} = (\mathbf{v}_1^{\mathsf{T}}, \ldots, \mathbf{v}_{N+1}^{\mathsf{T}})^{\mathsf{T}} \in \mathbb{R}^{2(N+1)}$ | 全局速度状态向量 | — | 系统核心未知量 |
| **约束参数** | $v_{\max}$ | 各把手最大安全速度 | m/s | 通常取$2\,\text{m/s}$ |
| | $a_{\max}$ | 最大加速度限制 | m/s² | 人体工程学约束 |

---

## 二、核心数学模型：从全局坐标出发的约束推导

### 2.1 刚性约束的完整流形描述

每节板凳由其前后两把手铰接定义，构成不可伸长的刚性杆。几何约束为：

$$\|\mathbf{r}_{i+1} - \mathbf{r}_i\|^2 = L_i^2, \quad i = 1, 2, \ldots, N \tag{1}$$

该约束定义了构型空间$\mathbb{R}^{2(N+1)}$中的$N$维子流形。对时间求导，得到速度层面的线性约束：

$$(\mathbf{v}_{i+1} - \mathbf{v}_i) \cdot (\mathbf{r}_{i+1} - \mathbf{r}_i) = 0 \tag{2}$$

引入全局已知的单位向量$\mathbf{e}_i = (\mathbf{r}_{i+1} - \mathbf{r}_i)/L_i$，约束$(2)$可写成简洁的标量形式：

$$\boxed{(\mathbf{v}_{i+1} - \mathbf{v}_i) \cdot \mathbf{e}_i = 0} \tag{3}$$

这是**单个标量约束**，而非向量约束。其物理意义明确：相邻两把手沿板凳长轴方向的相对速度必须为零，否则将违反刚性条件。系统共有$N$个此类标量约束，作用于$2(N+1)$个速度分量，故速度空间的自由度为：

$$\dim(\text{速度空间}) = 2(N+1) - N = N + 2 \tag{4}$$

这与物理直觉完全一致：$N+1$个质点本有$2(N+1)$个自由度，$N$个刚性约束各消除1个自由度，剩余$N+2$个自由度。其中2个对应整体的平动（刚体平移），$N$个对应各板凳独立的转动。

### 2.2 局部标架表示与坐标变换

若需在局部标架中分析问题，必须显式引入坐标变换。设第$i$节板凳的局部标架为$(\mathbf{e}_i, \mathbf{n}_i)$，则局部到全局的变换由旋转矩阵$\mathbf{R}(\phi_i)$实现：

$$\mathbf{v}_j = \mathbf{R}(\phi_i)\, \tilde{\mathbf{v}}_j^{(i)} = \begin{bmatrix} \cos\phi_i & -\sin\phi_i \\ \sin\phi_i & \cos\phi_i \end{bmatrix} \begin{bmatrix} v_{j,\parallel}^{(i)} \\ v_{j,\perp}^{(i)} \end{bmatrix} \tag{5}$$

**关键注意**：第$i+1$个把手同时属于第$i$节板凳（作为后把手）和第$i+1$节板凳（作为前把手），但其在两节板凳局部标架中的表示不同：

$$\mathbf{v}_{i+1} = \mathbf{R}(\phi_i)\, \tilde{\mathbf{v}}_{i+1}^{(i)} = \mathbf{R}(\phi_{i+1})\, \tilde{\mathbf{v}}_{i+1}^{(i+1)} \tag{6}$$

因此同一速度在不同标架中的分量满足：

$$\tilde{\mathbf{v}}_{i+1}^{(i)} = \mathbf{R}^{\mathsf{T}}(\phi_i)\mathbf{R}(\phi_{i+1})\, \tilde{\mathbf{v}}_{i+1}^{(i+1)} = \mathbf{R}(\phi_{i+1}-\phi_i)\, \tilde{\mathbf{v}}_{i+1}^{(i+1)} \tag{7}$$

将约束$(3)$用局部分量表示。注意到$\mathbf{e}_i$在全局坐标中为已知向量，直接计算：

$$(\mathbf{v}_{i+1} - \mathbf{v}_i) \cdot \mathbf{e}_i = \left[\mathbf{R}(\phi_i)\tilde{\mathbf{v}}_{i+1}^{(i)} - \mathbf{R}(\phi_i)\tilde{\mathbf{v}}_{i}^{(i)}\right] \cdot \mathbf{e}_i = \left(\tilde{\mathbf{v}}_{i+1}^{(i)} - \tilde{\mathbf{v}}_{i}^{(i)}\right) \cdot \mathbf{R}^{\mathsf{T}}(\phi_i)\mathbf{e}_i \tag{8}$$

由于$\mathbf{R}^{\mathsf{T}}(\phi_i)\mathbf{e}_i = (1, 0)^{\mathsf{T}}$，约束简化为：

$$\boxed{v_{i+1,\parallel}^{(i)} - v_{i,\parallel}^{(i)} = 0} \tag{9}$$

即**在第$i$节板凳的局部标架中，前后两把手的切向速度分量必须相等**。这与法向速度的关系共同构成完整的刚性杆速度约束。

### 2.3 角速度的精确定义与速度基点法

必须明确区分两种角速度定义：

**定义A（绕质心角速度）**：$\omega_i^{\text{cm}}$为板凳绕其质心$\mathbf{c}_i = (\mathbf{r}_i + \mathbf{r}_{i+1})/2$的角速度。

**定义B（绕前把手角速度）**：$\omega_i$为板凳绕其前把手$\mathbf{r}_i$的角速度。

采用定义B（更便于链式系统分析），应用**速度基点法**：刚体上任意点的速度等于基点速度加上绕基点转动的速度。以后把手$\mathbf{r}_{i+1}$为动点，前把手$\mathbf{r}_i$为基点：

$$\mathbf{v}_{i+1} = \mathbf{v}_i + \boldsymbol{\omega}_i \times (\mathbf{r}_{i+1} - \mathbf{r}_i) \tag{10}$$

在二维平面运动中，$\boldsymbol{\omega}_i = \omega_i \mathbf{k}$（垂直于平面的向量），叉积退化为：

$$\mathbf{v}_{i+1} = \mathbf{v}_i + \omega_i L_i \mathbf{n}_i \tag{11}$$

此即向量形式的**速度传递方程**。将其投影到$\mathbf{e}_i$和$\mathbf{n}_i$方向：

- **切向投影**：$\mathbf{v}_{i+1} \cdot \mathbf{e}_i = \mathbf{v}_i \cdot \mathbf{e}_i + 0$，即$v_{i+1,\parallel}^{(i)} = v_{i,\parallel}^{(i)}$，与$(9)$一致；
- **法向投影**：$\mathbf{v}_{i+1} \cdot \mathbf{n}_i = \mathbf{v}_i \cdot \mathbf{n}_i + \omega_i L_i$，即：

$$\boxed{v_{i+1,\perp}^{(i)} = v_{i,\perp}^{(i)} + \omega_i L_i} \tag{12}$$

方程$(11)$-$(12)$完整描述了单节板凳的速度传递关系。注意：法向速度**不守恒**，其差值恰好产生角速度效应。

### 2.4 全局约束方程组的矩阵形式

将$N$个标量约束$(3)$堆叠，定义约束矩阵$\mathbf{C} \in \mathbb{R}^{N \times 2(N+1)}$。第$i$行对应第$i$个约束：

$$\mathbf{C}_{i,2i-1:2i} = -\mathbf{e}_i^{\mathsf{T}} = (-\cos\phi_i, -\sin\phi_i), \quad \mathbf{C}_{i,2i+1:2i+2} = \mathbf{e}_i^{\mathsf{T}} = (\cos\phi_i, \sin\phi_i) \tag{13}$$

其余元素为零。则全局约束方程为：

$$\mathbf{C}\mathbf{V} = \mathbf{0} \tag{14}$$

该齐次线性方程组的解空间维数为$N+2$。为确定唯一解，需补充$N+2$个边界条件。典型取法：

- **龙头速度给定**：$\mathbf{v}_1 = \mathbf{v}_1^{\text{given}}$（2个条件）
- **龙头方向约束**：通常给定龙头切向速度$v_{1,\parallel}^{(1)} = v_1^{\text{given}}$，法向分量$v_{1,\perp}^{(1)} = 0$（若龙头沿自身方向运动）

实际求解时，可将$\mathbf{v}_1$作为已知量代入，剩余$2N$个未知量满足$N$个约束，再补充$N$个由运动学或优化条件确定的方程。

---

## 三、速度放大效应的严格分析

### 3.1 离散框架的曲率-速度关系

将板凳龙视为**离散标架曲线**（discrete framed curve），每节板凳对应曲线的一段弦。定义相邻板凳的**离散曲率**：

$$\kappa_i = \frac{2\tan(\psi_i/2)}{L_i^{\text{eff}}} \tag{15}$$

其中$\psi_i = \phi_{i+1} - \phi_i$为相邻板凳的夹角，$L_i^{\text{eff}} = (L_i + L_{i+1})/2$为有效长度。当$\psi_i \to 0$时，退化为连续曲率。

速度放大效应源于几何约束下的能量重分配。由$(11)$，速度幅值的平方为：

$$v_{i+1}^2 = \|\mathbf{v}_i + \omega_i L_i \mathbf{n}_i\|^2 = v_i^2 + 2\omega_i L_i (\mathbf{v}_i \cdot \mathbf{n}_i) + \omega_i^2 L_i^2 \tag{16}$$

利用$\mathbf{v}_i \cdot \mathbf{n}_i = v_{i,\perp}^{(i)}$并将$\omega_i$从$(12)$代入$\omega_i = (v_{i+1,\perp}^{(i)} - v_{i,\perp}^{(i)})/L_i$，经过代数运算可得：

$$v_{i+1}^2 = v_i^2 + (v_{i+1,\perp}^{(i)})^2 - (v_{i,\perp}^{(i)})^2 \tag{17}$$

这表明速度变化完全由法向速度分量的改变驱动。

### 3.2 螺线几何下的速度传递

对于盘入螺线，设螺线方程为$r = r_0 + p\theta/(2\pi)$（阿基米德螺线，$p$为螺距）。板凳沿螺线切向排列，故：

$$\phi_i = \theta_i + \frac{\pi}{2} \tag{18}$$

其中$\theta_i$为第$i$个把手的极角。螺线切向与径向的夹角$\alpha$满足$\tan\alpha = r/\dot{r} = r \cdot 2\pi/p$。

在螺线紧密盘绕区域（$r$较小），曲率半径$\rho \approx r/\sin\alpha \approx p/(2\pi)$为常数量级，但几何构型导致相邻板凳夹角$\psi_i$显著。设龙头以恒定速率$v_1$沿螺线运动，分析后续板凳的速度响应。

将速度分解到螺线切向$\mathbf{t}$和法向$\mathbf{n}_{\text{curve}}$（与板凳局部标架不同）。由刚性约束，各把手被"锁定"在螺线上，形成**非完整约束链**。对于小螺距、大曲率情形，几何分析表明：

$$\frac{v_{i+1}}{v_i} \approx \frac{\rho_{i+1}}{\rho_i} \cdot \frac{\cos\beta_i}{\cos\beta_{i+1}} \tag{19}$$

其中$\beta_i$为板凳方向与螺线切向的夹角，$\rho_i$为局部曲率半径。在螺线中心附近，$\rho \to 0$且板凳排列趋于径向，$\beta \to \pm\pi/2$，导致分母$\cos\beta_{i+1} \to 0$，产生显著的速度放大。

### 3.3 速度约束反解的优化表述

给定龙头速度$v_1$，求解各把手速度并检验安全约束，可表述为带约束的优化问题。实际应用中，更关键的是**反问题**：求最大龙头速度$v_1^{\max}$，使得所有把手速度满足$v_j \leq v_{\max}$。

由线性约束$(14)$，速度具有齐次性：若$\mathbf{V}$是解，则$\lambda\mathbf{V}$也是解。因此最大龙头速度与约束速度的关系为：

$$v_1^{\max} = \frac{v_{\max}}{\max_j \|\mathbf{V}^{(1)}_j\|} \tag{20}$$

其中$\mathbf{V}^{(1)}$为对应$v_1 = 1$的归一化解。这转化为计算**速度传递增益**：

$$\gamma = \max_{j=2,\ldots,N+1} \frac{v_j}{v_1} \tag{21}$$

则$v_1^{\max} = v_{\max}/\gamma$。

增益$\gamma$的解析估计：对于近似等曲率排列的$N$节板凳，利用递推$(16)$-$(17)$，在共振型构型（相邻板凳夹角交替变化）下，$\gamma$可随$N$指数增长；而在平滑螺线排列下，$\gamma$通常为$O(1)$量级，但在中心区域因几何奇异性出现局部峰值。

---

## 四、离散Frenet-Serret框架与连续极限

### 4.1 离散标架的运动学

定义第$i$节板凳的**离散Frenet标架**$\{\mathbf{F}_i\}$：以$\mathbf{e}_i$为切向，$\mathbf{n}_i$为法向，$\mathbf{k}$为副法向。相邻标架的变换由**离散曲率**和**离散挠率**（二维情形退化为符号）描述：

$$\mathbf{F}_{i+1} = \mathbf{R}(\psi_i)\mathbf{F}_i \tag{22}$$

其中$\psi_i$为标架转角。速度传递方程$(11)$在该框架下具有与连续Frenet-Serret公式的深刻类比。

### 4.2 向连续介质的渐近联系

当$L_i \to 0$，$N \to \infty$且$NL_i \to L_{\text{total}}$时，离散系统趋于**不可伸长杆**（inelastic rod）的连续模型。设弧长参数为$s$，连续极限下：

$$\frac{\partial \mathbf{r}}{\partial s} = \mathbf{e}(s), \quad \frac{\partial \mathbf{v}}{\partial s} = \omega(s)\mathbf{n}(s) \tag{23}$$

这正是Kirchhoff杆理论中的运动学约束。