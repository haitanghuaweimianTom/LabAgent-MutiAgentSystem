我将基于您的分析，建立完整的等距螺线盘入运动学数学模型。

---

## 等距螺线盘入运动学数学模型

### 1. 变量与参数定义

| 符号 | 类型 | 定义 | 单位/备注 |
|:---|:---|:---|:---|
| $t$ | 自变量 | 时间 | s |
| $\theta$ | 状态变量 | 极角（极坐标） | rad，顺时针递减 |
| $r$ | 导出变量 | 极径 | m |
| $s$ | 导出变量 | 弧长 | m |
| $(x, y)$ | 状态变量 | 直角坐标 | m |
| $v_0$ | 参数 | 龙头前把手恒定速度 | 1 m/s |
| $p$ | 参数 | 螺距 | 0.55 m |
| $b$ | 参数 | 螺线增长率 | $p/(2\pi)$ m/rad |
| $a$ | 参数 | 螺线初始半径 | 0 m（螺线过原点） |
| $\theta_0$ | 初值 | 初始极角 | $32\pi$ rad（第16圈） |
| $r_0$ | 初值 | 初始极径 | 8.8 m |
| $L_i$ | 参数 | 第 $i$ 节板凳长度 | m（龙头2.86m，龙身/龙尾1.65m） |
| $d_i$ | 参数 | 第 $i$ 节把手间距 | m（$L_i - 2\times0.275$） |
| $n$ | 参数 | 总板凳节数 | 223（1龙头+221龙身+1龙尾） |
| $(x_i, y_i)$ | 状态变量 | 第 $i$ 节板凳前把手位置 | m，$i=1,2,\ldots,n$ |
| $\theta_i$ | 状态变量 | 第 $i$ 节板凳对应的极角 | rad |
| $\vec{T}$ | 向量 | 单位切向量 | 无量纲 |
| $\vec{N}$ | 向量 | 单位法向量 | 无量纲 |
| $\kappa$ | 导出变量 | 曲率 | m$^{-1}$ |
| $\omega$ | 导出变量 | 角速度 | rad/s |

---

### 2. 核心数学公式体系

#### 2.1 螺线基础方程

**极坐标方程：**
$$r(\theta) = a + b\theta = b\theta \tag{1}$$

其中螺线参数：
$$b = \frac{p}{2\pi} = \frac{0.55}{2\pi} \approx 0.0875 \text{ m/rad} \tag{2}$$

**直角坐标参数方程：**
$$\boxed{x(\theta) = b\theta\cos\theta, \quad y(\theta) = b\theta\sin\theta} \tag{3}$$

**参数导数（切向量分量）：**
$$\frac{dx}{d\theta} = b(\cos\theta - \theta\sin\theta), \quad \frac{dy}{d\theta} = b(\sin\theta + \theta\cos\theta) \tag{4}$$

#### 2.2 弧长与运动学反问题

**弧长微元：**
$$ds = \sqrt{\left(\frac{dr}{d\theta}\right)^2 + r^2}\,d\theta = b\sqrt{1+\theta^2}\,d\theta \tag{5}$$

**弧长函数（从 $\theta$ 到 $\theta_0$ 的积分）：**
$$\boxed{s(\theta) = \frac{b}{2}\left[\theta_0\sqrt{1+\theta_0^2} - \theta\sqrt{1+\theta^2} + \text{arsinh}(\theta_0) - \text{arsinh}(\theta)\right]} \tag{6}$$

或等价表示为：
$$s(\theta) = \frac{b}{2}\left[\theta_0\sqrt{1+\theta_0^2} + \ln(\theta_0+\sqrt{1+\theta_0^2}) - \theta\sqrt{1+\theta^2} - \ln(\theta+\sqrt{1+\theta^2})\right] \tag{6'}$$

**龙头运动约束方程（隐式）：**
$$\boxed{s(\theta_1(t)) = v_0 t = t} \tag{7}$$

**数值求解框架——牛顿迭代：**
$$\theta^{(k+1)} = \theta^{(k)} - \frac{s(\theta^{(k)}) - t}{ds/d\theta\big|_{\theta^{(k)}}} = \theta^{(k)} - \frac{s(\theta^{(k)}) - t}{-b\sqrt{1+(\theta^{(k)})^2}} \tag{8}$$

#### 2.3 龙头速度与方向

**切向量的模：**
$$\left|\frac{d\vec{r}}{d\theta}\right| = \sqrt{\left(\frac{dx}{d\theta}\right)^2 + \left(\frac{dy}{d\theta}\right)^2} = b\sqrt{1+\theta^2} \tag{9}$$

**单位切向量：**
$$\boxed{\vec{T}(\theta) = \frac{(\cos\theta - \theta\sin\theta, \sin\theta + \theta\cos\theta)}{\sqrt{1+\theta^2}}} \tag{10}$$

**单位法向量（指向曲率中心，即螺线内侧）：**
$$\vec{N}(\theta) = \frac{(-\sin\theta - \theta\cos\theta, \cos\theta - \theta\sin\theta)}{\sqrt{1+\theta^2}} \tag{11}$$

**龙头速度向量：**
$$\vec{v}_1(t) = v_0 \cdot \vec{T}(\theta_1(t)) \tag{12}$$

**角速度关系（由链式法则）：**
$$\dot{\theta}_1 = \frac{d\theta_1}{dt} = \frac{d\theta_1}{ds}\cdot\frac{ds}{dt} = -\frac{v_0}{b\sqrt{1+\theta_1^2}} = -\frac{1}{b\sqrt{1+\theta_1^2}} \tag{13}$$

负号确认顺时针旋转（$\theta$ 递减）。

#### 2.4 龙身递推运动学（链式刚体约束）

**核心约束：** 相邻板凳通过把手刚性连接，第 $i$ 节板凳前把手与第 $i-1$ 节板凳后把手重合，且各节板凳长度固定。

**几何约束方程（第 $i$ 节与第 $i-1$ 节）：**
设第 $i$ 节板凳长度为 $L_i$（含把手孔距），把手孔中心距板头板尾各 $0.275$ m，故前把手到后把手间距为 $d_i = L_i - 0.55$ m。

第 $i$ 节板凳后把手位置：
$$(x_{i,\text{rear}}, y_{i,\text{rear}}) = (x_i, y_i) - d_i \cdot (\cos\phi_i, \sin\phi_i) \tag{14}$$

其中 $\phi_i$ 为第 $i$ 节板凳的朝向角。

**递推关系：** 第 $i$ 节板凳前把手 = 第 $i-1$ 节板凳后把手：
$$\boxed{(x_i, y_i) = (x_{i-1,\text{rear}}, y_{i-1,\text{rear}}), \quad i = 2, 3, \ldots, n} \tag{15}$$

**板凳朝向角确定：** 由于板凳中心线沿螺线切线方向（理想化假设），或更精确地，由于两端把手均在螺线上，需解非线性方程：

第 $i$ 节板凳前后把手均在螺线上，设对应极角为 $\theta_i$（前）和 $\tilde{\theta}_i$（后），满足：
$$\sqrt{[x(\theta_i)-x(\tilde{\theta}_i)]^2 + [y(\theta_i)-y(\tilde{\theta}_i)]^2} = d_i \tag{16}$$

且第 $i$ 节板凳前把手与第 $i-1$ 节后把手重合：
$$(x(\tilde{\theta}_{i-1}), y(\tilde{\theta}_{i-1})) = (x(\theta_i), y(\theta_i)) \tag{17}$$

**简化递推模型——切线近似：**
若假设各节板凳沿当地螺线切线方向，则：
$$\theta_i \approx \theta_{i-1} - \frac{d_{i-1}}{b\sqrt{1+\theta_{i-1}^2}} \cdot \frac{d\theta}{ds}\Big|_{\text{adjusted}} \tag{18}$$

更精确的数值方法：对给定 $\theta_{i-1}$，求解关于 $\theta_i$ 的非线性方程：
$$\boxed{[b\theta_i\cos\theta_i - b\tilde{\theta}_{i-1}\cos\tilde{\theta}_{i-1}]^2 + [b\theta_i\sin\theta_i - b\tilde{\theta}_{i-1}\sin\tilde{\theta}_{i-1}]^2 = d_{i-1}^2} \tag{19}$$

其中 $\tilde{\theta}_{i-1}$ 由前一步确定，且需选择使 $\theta_i < \tilde{\theta}_{i-1}$（向内盘入）的根。

#### 2.5 各点速度与加速度

**第 $i$ 节板凳前把手速度：**
由于刚性约束，速度方向沿当地螺线切向，大小由运动学传播确定。

**速度传播公式（微分形式）：**
对约束方程 $(x_i-x_{i-1,\text{rear}})^2 + (y_i-y_{i-1,\text{rear}})^2 = d_{i-1}^2$ 求导，结合各点速度沿切向的约束，可建立速度递推关系。

**角速度传播：**
设第 $i$ 节板凳绕其中心（或某参考点）的转动角速度为 $\dot{\phi}_i$，则：
$$\vec{v}_{i,\text{rear}} = \vec{v}_{i,\text{front}} + \dot{\phi}_i \hat{k} \times \vec{r}_{\text{rear/front}} \tag{20}$$

结合前后把手速度均沿螺线切向的约束，可解出 $\dot{\phi}_i$ 和速度大小。

---

### 3. 公式物理意义详解

**公式(1)-(3)：螺线几何表征**
阿基米德螺线的本质特征是极径与极角成正比，这保证了相邻两圈之间的径向距离（螺距）恒定。参数 $b$ 表征螺线的"张开速率"，$b$ 越小螺线越紧密。初始条件 $\theta_0 = 32\pi$ 对应第16圈，此时极径 $r_0 = 8.8$ m，为舞龙队伍提供了足够的初始盘旋空间。

**公式(5)-(7)：弧长参数化的反问题**
这是整个模型的核心难点。龙头以恒定速率 $v_0 = 1$ m/s运动，意味着弧长随时间线性增长 $s = v_0 t$。但弧长作为极角的函数 $s(\theta)$ 是超越函数，其反函数 $\theta(s)$ 无解析表达式。这反映了等距螺线的本质非线性：尽管几何上"等距"，但运动学上角速度非均匀——越靠近中心，相同弧长对应的角位移越大，旋转越快。

公式(6)中的 $\text{arsinh}(\theta) = \ln(\theta+\sqrt{1+\theta^2})$ 为反双曲正弦函数，其出现源于积分 $\int\sqrt{1+\theta^2}d\theta$ 的标准形式。当 $\theta \gg 1$ 时，$s \approx \frac{b}{2}\theta^2$（抛物线增长）；当 $\theta \to 0$ 时，$s \approx b\theta$（线性关系）。

**公式(10)-(13)：速度与方向分析**
单位切向量 $\vec{T}$ 的表达式揭示了螺线运动的方向特性：分子中的 $-\theta\sin\theta$ 和 $+\theta\cos\theta$ 项表明，随着 $\theta$ 增大（或减小），切向方向逐渐偏离径向而趋于角向。角速度公式(13)显示 $\dot{\theta} \propto -1/\sqrt{1+\theta^2}$，当 $\theta$ 较大时 $|\dot{\theta}| \approx 1/(b|\theta|)$，即靠近中心时角速度急剧增大——这是盘龙表演视觉效果的数学根源。

**公式(15)-(19)：链式刚体约束**
这些方程体现了"板凳龙"作为多体系统的核心力学特征。223节板凳通过把手连接形成运动链，每节板凳的运动受到前后邻居的约束。方程(19)是一个关于 $\theta_i$ 的超越方程，通常有两个解（对应螺线的不同分支），需根据物理情境选择正确的根（保证盘入方向一致且不自交）。

这种约束传播导致"运动延迟"现象：龙头的运动状态（位置、速度）以有限速度沿龙身传播，越靠后的节段对龙头运动的响应越滞后，且由于螺线曲率变化，这种延迟是非均匀的。

---

### 4. 模型假设

**假设1：理想等距螺线几何**
舞龙盘入轨迹严格遵循阿基米德螺线 $r = b\theta$，忽略实际表演中因地面摩擦、人员配合等因素导致的轨迹偏差。螺线过原点（$a=0$），螺距恒定 $p = 0.55$ m。

**假设2：龙头匀速运动**
龙头前把手速度严格保持 $v_0 = 1$ m/s，不随时间、位置变化。这意味着舞龙者能精确控制龙头速度，忽略加速、减速过程及人体运动的固有波动性。

**假设3：刚性板凳模型**
各节板凳为绝对刚体，不发生弯曲、伸缩或扭转变形。把手连接点为理想铰接，仅传递力而不传递力矩，允许相邻板凳间自由转动。

**假设4：二维平面运动**
所有运动限制在水平面内，忽略板凳的竖直振动、倾斜以及地面的三维不平度影响。

**假设5：无滑动纯滚动**
板凳把手与螺线轨迹的接触为理想几何约束，把手精确位于螺线上，无侧滑、无超前或滞后。

**假设6：连续介质近似**
尽管板凳为离散节段，但在运动学分析中将把手位置视为连续变量，相邻节段间的角度差足够小，允许使用微分关系。

**假设7：忽略空气阻力与摩擦**
不考虑空气对龙身的气动作用，以及板凳与地面、板凳之间的摩擦效应，系统机械能守恒（对龙头匀速驱动的情形，意味着有外部能量输入维持恒定速度）。

**假设8：初始构型一致性**
$t=0$ 时刻整个龙身完全位于螺线上，各节板凳位置满足螺线几何约束，无初始松弛或张紧。

**假设9：单值性条件**
运动过程中螺线不自交，且龙身各节段互不穿透。这要求对给定的螺线参数和板凳长度，存在最小可行极角 $\theta_{\min}$，当 $\theta < \theta_{\min}$ 时模型失效（需考虑碰撞避免）。

**假设10：准静态响应**
龙身各节段对龙头运动变化的响应是瞬时的，即忽略弹性波在龙身中的传播时间，认为约束方程在所有时刻严格满足。

---

### 5. 模型求解策略

基于上述模型，实际计算需采用以下数值策略：

1. **时间离散化**：将总时间 $T$ 分为步长 $\Delta t$ 的小区间
2. **龙头位置求解**：对每个时刻 $t_k$，用牛顿迭代法解 $s(\theta_1) = t_k$ 得 $\theta_1(t_k)$
3. **龙身递推求解**：从龙头开始，逐节数值求解方程(19)得 $\theta_i(t_k)$
4. **速度与加速度**：通过中心差分或解析微分计算各点速度、加速度
5. **碰撞检测**：监控相邻节段距离，判断是否满足假设9

该模型完整刻画了等距螺线盘入运动的几何约束与运动学传播机制，为后续分析盘出策略、碰撞避免及优化调度奠定了数学基础。模型的核心非线性源于弧长-角度关系的超越性，以及链式约束的耦合性，这要求必须借助数值方法获得具体结果。

我将基于您的分析，建立盘入终止时刻碰撞检测的完整数学模型。

---

## 盘入终止时刻碰撞检测的数学模型

### 一、变量与参数定义

| 符号 | 类型 | 含义 | 单位/备注 |
|:---|:---|:---|:---|
| **系统参数** |
| $N$ | 常数 | 板凳总数 | $N = 223$ |
| $b$ | 常数 | 螺线系数 | $b = 55/(2\pi) \approx 8.756$ cm/rad |
| $p$ | 常数 | 螺距 | $p = 55$ cm |
| **几何参数** |
| $L_1$ | 常数 | 龙头板凳孔间距 | $L_1 = 286$ cm |
| $L_k\,(k\geq 2)$ | 常数 | 龙身/龙尾板凳孔间距 | $L_k = 165$ cm |
| $l_1$ | 常数 | 龙头板凳板长 | $l_1 = 341$ cm |
| $l_k\,(k\geq 2)$ | 常数 | 龙身/龙尾板凳板长 | $l_k = 220$ cm |
| $w$ | 常数 | 板凳板宽的一半 | $w = 15$ cm（全宽30 cm） |
| $h$ | 常数 | 把手孔径 | $h = 5.5$ cm（半径） |
| **运动变量** |
| $t$ | 自变量 | 时间 | s |
| $\theta_1(t)$ | 函数 | 龙头前把手螺线参数 | rad |
| $\theta_k(t)$ | 隐函数 | 第$k$节前把手螺线参数 | rad, $k=2,\ldots,N$ |
| $\mathbf{r}(\theta)$ | 向量函数 | 螺线参数方程 | cm |
| **构型变量** |
| $\mathbf{p}_k$ | 向量 | 第$k$节板凳前把手位置 | $\mathbf{p}_k = \mathbf{r}(\theta_k)$ |
| $\mathbf{q}_k$ | 向量 | 第$k$节板凳后把手位置 | $\mathbf{q}_k = \mathbf{r}(\theta_{k+1}) = \mathbf{p}_{k+1}$ |
| $\mathbf{c}_k$ | 向量 | 第$k$节板凳几何中心 | cm |
| $\mathbf{t}_k$ | 单位向量 | 板凳长轴方向（切向） | — |
| $\mathbf{n}_k$ | 单位向量 | 板凳短轴方向（法向） | $\mathbf{n}_k \perp \mathbf{t}_k$ |
| **碰撞检测变量** |
| $\mathcal{R}_k$ | 集合 | 第$k$节板凳占据的矩形区域 | $\mathbb{R}^2$ 中的闭凸集 |
| $d_{ij}$ | 函数 | 板凳对$(i,j)$间的有符号距离 | cm, $d_{ij}<0$ 表示碰撞 |
| $\mathcal{C}$ | 集合 | 碰撞约束流形 | $\mathcal{C} = \{\theta_1 : \exists(i,j), d_{ij} \leq 0\}$ |

---

### 二、核心数学模型

#### 2.1 阿基米德螺线约束流形

螺线参数方程定义系统的基本运动约束：

$$\mathbf{r}(\theta) = \begin{pmatrix} b\theta\cos\theta \\ b\theta\sin\theta \end{pmatrix}, \quad \theta \in [0, +\infty) \tag{1}$$

其中螺线系数 $b = p/(2\pi) = 55/(2\pi)$ cm/rad，保证相邻螺线臂的径向距离恒为螺距 $p = 55$ cm。

**物理意义**：方程(1)描述了极坐标下 $r = b\theta$ 的等距螺线在笛卡尔坐标系中的参数表示。参数 $\theta$ 同时承担角度与"高度"的双重角色——随着 $\theta$ 增大，点沿螺线由内向外（盘入）或向外向内（盘出）运动，且径向间距保持恒定。

#### 2.2 链式刚体系统的递推约束

龙头前把手作为系统驱动，其运动 $\theta_1(t)$ 唯一确定整个系统构型。后续把手位置由孔间距约束隐式确定：

$$\|\mathbf{r}(\theta_{k-1}) - \mathbf{r}(\theta_k)\| = L_{k-1}, \quad k = 2, 3, \ldots, N \tag{2}$$

该递推方程可改写为关于 $\theta_k$ 的隐式方程。定义距离函数：

$$F_k(\theta; \theta_{k-1}) := \|\mathbf{r}(\theta_{k-1}) - \mathbf{r}(\theta)\|^2 - L_{k-1}^2 = 0 \tag{3}$$

展开得：

$$b^2[\theta_{k-1}^2 + \theta^2 - 2\theta_{k-1}\theta\cos(\theta_{k-1}-\theta)] = L_{k-1}^2 \tag{4}$$

**物理意义**：方程(2)-(4)构成系统的**完整约束链**。由于板凳通过刚性把手连接，相邻把手间距固定不变。该约束将 $N$ 个刚体的 $3N$ 个自由度压缩至单个自由度（由 $\theta_1$ 参数化），系统的构型空间 $\mathcal{Q}$ 实质为一维流形：

$$\mathcal{Q} = \{\mathbf{q}(\theta_1) \in \mathbb{R}^{3N} : \text{约束}(2)\text{对所有 }k\geq 2\text{ 成立}\} \cong S^1 \text{ 或 } \mathbb{R}^1 \tag{5}$$

#### 2.3 单节板凳的刚体变换与几何表示

对于第 $k$ 节板凳，基于前后把手位置建立局部标架：

**长轴方向向量**（沿龙身切线方向）：
$$\mathbf{t}_k = \frac{\mathbf{q}_k - \mathbf{p}_k}{\|\mathbf{q}_k - \mathbf{p}_k\|} = \frac{\mathbf{r}(\theta_{k+1}) - \mathbf{r}(\theta_k)}{L_k} \tag{6}$$

**法向量**（由 $\mathbf{t}_k$ 逆时针旋转 $90^\circ$）：
$$\mathbf{n}_k = \begin{pmatrix} 0 & -1 \\ 1 & 0 \end{pmatrix} \mathbf{t}_k = \begin{pmatrix} -t_{k,y} \\ t_{k,x} \end{pmatrix} \tag{7}$$

**板凳几何中心**（考虑把手位于板宽中央，板体向法向一侧偏移 $w = 15$ cm）：
$$\mathbf{c}_k = \frac{\mathbf{p}_k + \mathbf{q}_k}{2} + w \cdot \mathbf{n}_k \tag{8}$$

**物理意义**：方程(6)-(8)建立了从"把手点约束"到"连续板体几何"的映射。由于把手孔位于板凳板宽的中心线上，而板体向运动方向的左侧（逆时针方向）延伸宽度 $w$，故中心需沿法向 $\mathbf{n}_k$ 偏移。这一偏移对碰撞检测至关重要——忽略将导致系统性的位置偏差。

#### 2.4 矩形板凳的凸体表示

第 $k$ 节板凳作为矩形板，其占据空间为：

$$\mathcal{R}_k = \left\{\mathbf{x} \in \mathbb{R}^2 : \mathbf{x} = \mathbf{c}_k + u \cdot \mathbf{t}_k + v \cdot \mathbf{n}_k,\, |u| \leq \frac{l_k}{2},\, |v| \leq w \right\} \tag{9}$$

等价地，用支撑函数或四个顶点表示。设半长 $a_k = l_k/2$，半宽 $b = w = 15$ cm，则四个顶点为：

$$\mathbf{v}_k^{(\pm,\pm)} = \mathbf{c}_k \pm a_k \mathbf{t}_k \pm b \mathbf{n}_k \tag{10}$$

**物理意义**：方程(9)-(10)将理想化的"线段"（把手连线）扩展为具有实际尺寸的矩形区域。板凳的几何由中心 $\mathbf{c}_k$、局部标架 $(\mathbf{t}_k, \mathbf{n}_k)$ 及半轴长 $(a_k, b)$ 完全确定，构成 $\mathbb{R}^2$ 中的闭凸集。

#### 2.5 分离轴定理（SAT）下的碰撞检测

对于任意两节非相邻板凳 $\mathcal{R}_i$ 与 $\mathcal{R}_j$（要求 $|i-j| \geq 2$，相邻板凳自然不相交由构造保证），碰撞判定基于分离轴定理：

**定理（分离轴）**：两个凸多边形不相交，当且仅当存在一条分离轴，使得两多边形在该轴上的投影不重叠。对于矩形，仅需检测两矩形各边方向共4条候选轴。

定义投影算子：对于单位方向 $\mathbf{d}$，集合 $\mathcal{S}$ 的投影为区间 $[\min_{\mathbf{x}\in\mathcal{S}} \mathbf{d}\cdot\mathbf{x}, \max_{\mathbf{x}\in\mathcal{S}} \mathbf{d}\cdot\mathbf{x}]$。

对于矩形 $\mathcal{R}_k$，其在方向 $\mathbf{d}$ 上的投影半径为：
$$\rho_k(\mathbf{d}) = a_k |\mathbf{d}\cdot\mathbf{t}_k| + b |\mathbf{d}\cdot\mathbf{n}_k| \tag{11}$$

两矩形中心连线在方向 $\mathbf{d}$ 上的投影：
$$\delta_{ij}(\mathbf{d}) = \mathbf{d}\cdot(\mathbf{c}_i - \mathbf{c}_j) \tag{12}$$

**碰撞判定条件**：若存在方向 $\mathbf{d} \in \{\mathbf{t}_i, \mathbf{n}_i, \mathbf{t}_j, \mathbf{n}_j\}$ 使得
$$|\delta_{ij}(\mathbf{d})| > \rho_i(\mathbf{d}) + \rho_j(\mathbf{d}) \tag{13}$$

则 $\mathcal{R}_i \cap \mathcal{R}_j = \emptyset$（无碰撞）；反之，若对所有4条轴均不满足(13)，则 $\mathcal{R}_i \cap \mathcal{R}_j \neq \emptyset$（发生碰撞）。

**有符号距离函数**（量化穿透深度）：
$$d_{ij} = \max_{\mathbf{d}\in\{\mathbf{t}_i,\mathbf{n}_i,\mathbf{t}_j,\mathbf{n}_j\}} \left[\rho_i(\mathbf{d}) + \rho_j(\mathbf{d}) - |\delta_{ij}(\mathbf{d})|\right] \tag{14}$$

则：
$$d_{ij} \leq 0 \Leftrightarrow \mathcal{R}_i \cap \mathcal{R}_j = \emptyset, \quad d_{ij} > 0 \Leftrightarrow \text{发生碰撞且 } d_{ij} \text{ 为最小穿透深度} \tag{15}$$

**物理意义**：方程(13)-(15)将几何交集问题转化为有限维优化判定。分离轴定理利用凸集的线性可分性，将复杂的二维区域交集检测降维为4个一维区间重叠检测。有符号距离 $d_{ij}$ 不仅给出布尔碰撞结果，还量化碰撞严重程度——在终止时刻判定中，我们关注首次满足 $\max_{i,j} d_{ij} = 0^+$ 的临界状态。

#### 2.6 盘入终止时刻的优化模型

设龙头以恒定角速度 $\omega = \dot{\theta}_1$ 盘入（或更一般地，给定 $\theta_1(t)$），终止时刻 $t^*$ 定义为系统首次触及自碰撞边界的时刻：

$$t^* = \inf\left\{t > 0 : \max_{\substack{1 \leq i < j \leq N \\ |i-j| \geq 2}} d_{ij}(\theta_1(t)) \geq 0 \right\} \tag{16}$$

等价地，定义系统构型的碰撞指标函数：

$$\Phi(\theta_1) = \min_{\substack{1 \leq i < j \leq N \\ |i-j| \geq 2}} \left[-d_{ij}(\theta_1)\right] \tag{17}$$

则终止条件为：
$$\Phi(\theta_1^*) = 0, \quad \text{且} \quad \Phi(\theta_1) > 0 \text{ 对所有 } \theta_1 > \theta_1^* \text{ 在邻域内成立} \tag{18}$$

即 $\theta_1^*$ 为 $\Phi$ 的**首个根**。

**物理意义**：方程(16)-(18)将"何时停止"的物理问题转化为碰撞流形 $\mathcal{C} = \{\theta_1 : \Phi(\theta_1) \leq 0\}$ 的首次穿越问题。由于螺线盘入过程中龙身逐渐收紧，板凳间距离单调减小，碰撞指标 $\Phi(\theta_1)$ 随 $\theta_1$ 增大而递减，保证根的唯一性。

---

### 三、模型假设

| 编号 | 假设内容 | 数学表述 | 合理性说明 |
|:---|:---|:---|:---|
| **A1** | **理想刚体假设** | 所有板凳为不可变形的刚体，把手孔为理想点 | 竹木质板凳在舞龙动态载荷下变形微小，可忽略弹性效应 |
| **A2** | **平面运动假设** | 系统运动约束于水平面 $\mathbb{R}^2$，忽略三维起伏 | 标准舞龙场地为平坦地面，龙头高度变化不影响盘入平面投影 |
| **A3** | **理想螺线约束** | 龙头前把手严格沿阿基米德螺线 $r=b\theta$ 运动 | 实际路径由舞龙者控制，但训练有素的队伍可近似该轨迹 |
| **A4** | **无滑动铰链** | 把手连接为理想铰链，仅传递力不限制相对转动 | 把手穿孔为间隙配合（孔径5.5cm，把手直径略小），转动自由度充分 |
| **A5** | **恒定螺距** | 螺线系数 $b$ 全程恒定，无螺距渐变 | 标准盘入动作保持等距螺线，螺距55cm为传统参数 |
| **A6** | **忽略孔径尺寸** | 把手视为几何点，孔径5.5cm不占用板体空间 | 孔径远小于板宽（30cm）和孔间距（165/286cm），对碰撞边界影响可忽略 |
| **A7** | **瞬时碰撞判定** | 碰撞检测基于准静态构型，忽略碰撞动力学响应 | 终止时刻判定为几何接触瞬间，不涉及碰撞后的动量交换 |
| **A8** | **相邻豁免** | 仅检测非相邻板凳对 $(i,j)$ 满足 $\|i-j\| \geq 2$ | 相邻板凳由构造保证间距 $L_k > l_k/2 + l_{k+1}/2$，不可能碰撞 |
| **A9** | **单调盘入** | 龙头参数 $\theta_1(t)$ 随时间严格单调递增 | 盘入过程为单向收紧，无往返或停滞 |
| **A10** | **均匀材质** | 板凳质量分布均匀，质心与几何中心重合 | 标准制作工艺保证对称性，不影响纯几何碰撞检测 |

---

### 四、模型求解框架

基于上述模型，盘入终止时刻的数值求解流程为：

**步骤1（前向递推）**：给定当前 $\theta_1$，由方程(4)数值求解 $\theta_2, \theta_3, \ldots, \theta_N$，采用牛顿迭代：
$$\theta_k^{(m+1)} = \theta_k^{(m)} - \frac{F_k(\theta_k^{(m)}; \theta_{k-1})}{\partial F_k/\partial \theta}\bigg|_{\theta_k^{(m)}} \tag{19}$$

**步骤2（构型计算）**：由 $(\theta_k)_{k=1}^N$ 计算所有 $\mathbf{p}_k, \mathbf{q}_k, \mathbf{c}_k, \mathbf{t}_k, \mathbf{n}_k$。

**步骤3（碰撞检测）**：对所有 $O(N^2)$ 板凳对执行SAT检测，或利用空间划分（如螺线邻域启发）降低至 $O(N)$ 候选对。

**步骤4（根定位）**：采用二分法或割线法求解 $\Phi(\theta_1^*) = 0$，精度控制为 $|d_{ij}| < \varepsilon = 10^{-3}$ cm。

该模型完整刻画了从运动学约束到几何碰撞的数学结构，为盘入终止时刻的精确判定提供了严谨的形式化基础。

我将基于您的分析，建立最小螺距优化问题的完整数学模型。

---

## 最小螺距优化问题的数学模型

### 一、变量与参数定义

| 类别 | 符号 | 含义 | 单位/类型 |
|:---|:---|:---|:---|
| **决策变量** | $p$ | 螺距（优化目标） | m |
| **导出参数** | $b = p/(2\pi)$ | 阿基米德螺线系数 | m/rad |
| **几何参数** | $w = 0.3$ | 板凳宽度 | m |
| | $h = 0.15$ | 板凳厚度/高度 | m |
| | $L_1 = 2.86$ | 龙头前后把手孔间距 | m |
| | $L_k = 1.65$（$k\geq 2$） | 龙身、龙尾孔间距 | m |
| | $l_1 = 3.41$ | 龙头板长（含把手） | m |
| | $l_k = 2.20$（$k\geq 2$） | 龙身、龙尾板长 | m |
| **系统规模** | $n = 223$ | 板凳总节数 | — |
| | $m = 224$ | 把手总数（含首尾） | — |
| **运动参数** | $v_0 = 1$ | 龙头前把手恒定速率 | m/s |
| **状态变量** | $\theta_k(t)$ | 第$k$个把手的极角 | rad |
| | $\mathbf{r}_k(t)$ | 第$k$个把手的位置向量 | m |
| | $\mathbf{c}_k(t)$ | 第$k$节板凳中心位置 | m |
| | $\phi_k(t)$ | 第$k$节板凳方向角 | rad |
| **辅助变量** | $\mathcal{F}(p)$ | 可行性指示函数 | $\{0, 1\}$ |
| | $p^*$ | 最优螺距（最小可行螺距） | m |

---

### 二、核心数学模型

#### 2.1 阿基米德螺线运动学框架

系统运动基于阿基米德螺线，其极坐标方程为：

$$\boxed{r = b\theta = \frac{p}{2\pi}\theta} \tag{1}$$

其中$r$为极径，$\theta$为极角。螺线参数$b$与螺距$p$的关系由式(1)确定，即螺线每旋转一周（$\Delta\theta = 2\pi$），极径增加量为$p$。

第$k$个把手在直角坐标系中的位置由极坐标转换得到：

$$\boxed{\mathbf{r}_k(\theta_k) = b\theta_k(\cos\theta_k, \sin\theta_k) = \frac{p\theta_k}{2\pi}(\cos\theta_k, \sin\theta_k)} \tag{2}$$

**物理意义**：式(2)建立了螺线参数空间（极角$\theta_k$）到物理空间（直角坐标$\mathbf{r}_k$）的映射。随着$\theta_k$增大，把手沿螺线向外运动；随着$\theta_k$减小，把手向中心盘入。参数$b$（或等价地，$p$）控制螺线的"松紧程度"——$p$越小，螺线越紧密，相邻圈间距越小，碰撞风险越高。

龙头前把手以恒定速率$v_0$沿螺线运动，其弧长微分关系为：

$$\mathrm{d}s = \sqrt{r^2 + \left(\frac{\mathrm{d}r}{\mathrm{d}\theta}\right)^2}\mathrm{d}\theta = b\sqrt{\theta^2 + 1}\,\mathrm{d}\theta \tag{3}$$

由此得到龙头前把手极角$\theta_1(t)$的隐式运动方程：

$$\boxed{v_0 t = b\int_{\theta_1(t)}^{\theta_1(0)}\sqrt{u^2+1}\,\mathrm{d}u = \frac{b}{2}\left[u\sqrt{u^2+1} + \ln(u+\sqrt{u^2+1})\right]_{\theta_1(t)}^{\theta_1(0)}} \tag{4}$$

**物理意义**：式(4)描述了龙头前把手沿螺线运动的"时间-角度"关系。由于弧长与极角之间不存在简单的线性关系，龙头运动具有**非均匀角速度**特征——即使线速度恒定，角速度$\dot{\theta}_1$随极径减小而增大（越靠近中心，转动越快）。该积分方程需数值求解以获得$\theta_1(t)$。

---

#### 2.2 链式刚体系统的几何约束

对于给定螺距$p$和龙头前把手轨迹$\theta_1(t)$，后续各把手位置由**等距约束**递推确定：

$$\boxed{\|\mathbf{r}_k - \mathbf{r}_{k+1}\| = L_k, \quad k = 1, 2, \ldots, 223} \tag{5}$$

其中$L_k$为第$k$与第$k+1$个把手之间的固定孔间距。

**物理意义**：式(5)构成**224维非线性方程组**，刻画了板凳龙作为链式刚体系统的本质特征。每节板凳通过两端的把手孔与相邻板凳铰接，形成不可伸长的运动链。该约束具有**强耦合性**：第$k+1$个把手的位置依赖于第$k$个把手，误差沿链条传递。对于给定$\theta_k$和待求$\theta_{k+1}$，需在螺线上寻找满足距离约束的点，这通常需要数值求解（如牛顿迭代法）。

具体求解时，设已知$\mathbf{r}_k$，求$\mathbf{r}_{k+1}$对应极角$\theta_{k+1}$。由式(2)和(5)：

$$\left[b\theta_k\cos\theta_k - b\theta_{k+1}\cos\theta_{k+1}\right]^2 + \left[b\theta_k\sin\theta_k - b\theta_{k+1}\sin\theta_{k+1}\right]^2 = L_k^2$$

化简得：

$$\boxed{b^2\left[\theta_k^2 + \theta_{k+1}^2 - 2\theta_k\theta_{k+1}\cos(\theta_k - \theta_{k+1})\right] = L_k^2} \tag{6}$$

**物理意义**：式(6)是关于$\theta_{k+1}$的超越方程，通常存在两个解（对应螺线"内侧"和"外侧"），需根据物理连续性选择正确分支（盘入过程中$\theta_{k+1} > \theta_k$，即后把手极角更大，位于龙头外侧）。

---

#### 2.3 板凳位姿与碰撞检测

第$k$节板凳的**中心位置**由两端把手位置平均确定：

$$\boxed{\mathbf{c}_k = \frac{\mathbf{r}_k + \mathbf{r}_{k+1}}{2}, \quad k = 1, 2, \ldots, 223} \tag{7}$$

**方向角**由把手连线确定：

$$\boxed{\phi_k = \arctan2\left((\mathbf{r}_{k+1} - \mathbf{r}_k)_y, (\mathbf{r}_{k+1} - \mathbf{r}_k)_x\right)} \tag{8}$$

其中$\arctan2(\cdot,\cdot)$为四象限反正切函数。

**物理意义**：式(7)-(8)将离散的把手位置转化为连续的刚体位姿。每节板凳视为以$\mathbf{c}_k$为中心、方向角为$\phi_k$的矩形刚体，其四个顶点在局部坐标系中为$(\pm l_k/2, \pm w/2)$，通过旋转矩阵变换到全局坐标系。

碰撞检测采用**分离轴定理（Separating Axis Theorem, SAT）**。对于任意两节非相邻板凳$(i,j)$（$|i-j| \geq 2$），定义其碰撞指示函数：

$$\boxed{\mathcal{C}_{ij}(t) = \begin{cases} 1, & \text{若矩形 } i \text{ 与矩形 } j \text{ 相交} \\ 0, & \text{若两矩形分离} \end{cases}} \tag{9}$$

系统整体碰撞状态为：

$$\boxed{\mathcal{C}(t) = \bigvee_{|i-j|\geq 2}\mathcal{C}_{ij}(t)} \tag{10}$$

**物理意义**：式(9)-(10)实现了从连续刚体位姿到离散碰撞判定的转换。SAT定理指出：两个凸多边形不相交，当且仅当存在某条分离轴，使得两多边形在该轴上的投影不重叠。对于矩形，只需检测4条候选轴（两矩形各2条边的法向）。式(10)的"或"运算表明：**任意一对非相邻板凳碰撞即导致系统失效**。

---

#### 2.4 可行性判定与优化目标

对于给定螺距$p$，系统从初始时刻$t=0$开始盘入，定义**碰撞首达时间**：

$$\boxed{T_{\text{collision}}(p) = \inf\{t \geq 0 : \mathcal{C}(t) = 1\}} \tag{11}$$

若系统能完成完整盘入（龙头到达螺线中心或指定终止条件），则$T_{\text{collision}}(p) = +\infty$。

**可行性指示函数**定义为：

$$\boxed{\mathcal{F}(p) = \begin{cases} 1, & T_{\text{collision}}(p) = +\infty \text{（或超过盘入总时长）} \\ 0, & T_{\text{collision}}(p) < +\infty \end{cases}} \tag{12}$$

**物理意义**：式(11)-(12)将复杂的时空演化过程压缩为二元可行性判定。$T_{\text{collision}}(p)$是螺距$p$的隐式、非光滑、甚至不连续的函数——微小改变$p$可能导致碰撞模式剧变。这种"黑箱"特性排除了基于梯度的优化方法。

最终，**最小螺距优化问题**表述为：

$$\boxed{p^* = \min_{p > 0}\{p : \mathcal{F}(p) = 1\}} \tag{13}$$

或等价地：

$$\boxed{p^* = \arg\min_{p \in \mathcal{P}_{\text{feasible}}} p, \quad \mathcal{P}_{\text{feasible}} = \{p > 0 : \mathcal{F}(p) = 1\}} \tag{14}$$

**物理意义**：式(13)-(14)是问题的最终数学凝练。最优螺距$p^*$是可行螺距集合的下确界，具有**临界性**特征：$p < p^*$时系统必然碰撞，$p \geq p^*$时（局部）可行。这种临界性源于几何约束的紧致性——最优解处通常存在"刚好接触"的板凳对，形成**活跃约束（active constraint）**。

---

### 三、公式物理意义系统阐释

上述公式体系构建了从微观几何到宏观优化的完整链条：

| 公式层级 | 核心公式 | 物理内涵 |
|:---|:---|:---|
| **运动学基础** | (1)-(4) | 单个质点（龙头把手）在螺线上的受约束运动 |
| **链式耦合** | (5)-(6) | 多体系统的几何约束传播，体现"龙头一动，全身皆动" |
| **刚体位姿** | (7)-(8) | 从离散铰接点到连续刚体的升维描述 |
| **碰撞判定** | (9)-(10) | 高维构型空间到二元安全状态的降维投影 |
| **优化决策** | (11)-(14) | 时空演化过程的终极压缩，寻找安全与紧凑的临界平衡 |

模型的核心难点在于**多尺度耦合**：螺距$p$（厘米量级变化）通过非线性映射(2)-(6)影响224个把手的全局构型，再通过SAT碰撞检测产生不连续的可行性跳跃。这种"蝴蝶效应"使得$p^*$的确定必须依赖数值搜索，且需要精细的离散化策略以保证精度。

---

### 四、模型假设

**假设1（理想螺线运动）**：龙头前把手严格沿阿基米德螺线(1)运动，无滑动、无偏离，线速度恒为$v_0 = 1$ m/s。

*合理性*：题目设定龙头以恒定速率盘入，忽略地面摩擦、把手间隙等微观效应。

**假设2（刚性板凳假设）**：所有板凳为理想刚体，无弹性变形；把手孔位于板凳端点，孔径忽略（视为点铰接）。

*合理性*：木质板凳的弹性模量远大于运动中的惯性力，变形可忽略；孔径（约5.5 cm）相对于板长（2-3 m）为小量。

**假设3（平面运动假设）**：所有运动限制在水平面内，忽略板凳的俯仰、侧倾及竖直方向运动。

*合理性*：舞龙表演在平坦地面进行，板凳厚度$h=0.15$ m远小于水平尺度，三维效应可忽略。

**假设4（非相邻碰撞原则）**：仅检测$|i-j| \geq 2$的板凳对碰撞，相邻板凳（$|i-j|=1$）因铰接关系自然分离。

*合理性*：相邻板凳通过把手铰接，其距离恒为$L_k$，不可能穿透；但需注意相邻板凳的矩形包络可能在极端弯曲时接触，实际计算中可扩展检测范围。

**假设5（初始条件确定性）**：初始时刻$t=0$时，系统处于螺线上完全伸展的已知构型，各把手极角$\theta_k(0)$由递推确定。

*合理性*：题目隐含盘龙从静止伸展状态开始盘入，初始构型由螺距$p$唯一确定。

**假设6（碰撞终止准则）**：一旦检测到任意非相邻板凳对碰撞，即判定该螺距不可行；不追究碰撞后的动力学演化。

*合理性*：优化目标为"无碰撞盘入"，碰撞即意味着任务失败，后续运动无物理意义。

**假设7（螺距均匀性）**：全过程中螺距$p$保持恒定，不考虑变螺距螺线。

*合理性*：题目要求"最小螺距"为常数，且实际制作中螺线模板具有固定螺距。

---

### 五、模型求解策略说明

基于上述模型，$p^*$的数值求解需采用**根搜索策略**：

1. **确定搜索区间**：下界$p_{\min} = w = 0.3$ m（几何必要），上界$p_{\max} = 0.55$ m（题目基准）或更大
2. **可行性判定子程序**：对给定$p$，数值积分式(4)得$\theta_1(t)$，递推求解式(6)得全系统轨迹，实时检测式(10)
3. **二分/黄金分割搜索**：利用$\mathcal{F}(p)$的单调性（通常$p$增大则可行性提高），收敛至$p^*$

该模型的计算复杂度为$O(T/\Delta t \cdot n^2)$，其中$T$为盘入总时长，$\Delta t$为时间步长，$n=223$为板凳数。碰撞检测的$O(n^2)$瓶颈可通过空间划分（如均匀网格）优化至$O(n)$。

---

本模型完整刻画了最小螺距优化问题的数学结构，为后续数值算法设计与实现奠定了理论基础。

我将基于您的分析，建立S形调头曲线几何优化与运动衔接的完整数学模型。

---

## S形调头曲线几何优化与运动衔接的数学模型

### 一、变量与参数定义

| 类别 | 符号 | 定义 | 单位 |
|:---|:---|:---|:---|
| **几何参数** | $R_D$ | 调头空间边界圆半径 | m |
| | $R_1, R_2$ | 前、后段圆弧半径 | m |
| | $\alpha_1, \alpha_2$ | 前、后段圆弧圆心角 | rad |
| | $s$ | 弧长参数 | m |
| | $L_T$ | 调头曲线总长度 | m |
| **曲线参数** | $\mathbf{r}(s)$ | 曲线位置向量 | m |
| | $\mathbf{T}(s)$ | 单位切向量 | — |
| | $\mathbf{N}(s)$ | 单位法向量 | — |
| | $\kappa(s)$ | 曲率 | m⁻¹ |
| | $\tau(s)$ | 挠率（平面曲线为零） | m⁻¹ |
| **螺线参数** | $p_{in}, p_{out}$ | 盘入、盘出螺线螺距 | m |
| | $a_{in}, a_{out}$ | 盘入、盘出螺线极径系数 | m/rad |
| | $\theta_{in}, \theta_{out}$ | 盘入、盘出螺线极角 | rad |
| **运动学参数** | $v_0$ | 龙头把手恒定速率 | m/s |
| | $\omega(s)$ | 角速度 | rad/s |
| | $a_t, a_n$ | 切向、法向加速度 | m/s² |
| **链式结构参数** | $n$ | 板凳节数 | — |
| | $L_0$ | 龙头板长（孔间距） | m |
| | $L_i\ (i\geq1)$ | 龙身/龙尾板长 | m |
| | $w$ | 板凳宽度 | m |
| | $d_{min}$ | 最小安全间距 | m |
| **优化变量** | $\mathbf{q}=(R_1,R_2,\alpha_1,\alpha_2,\mathbf{c}_1,\mathbf{c}_2)^T$ | 双圆弧参数向量 | — |
| | $\mathbf{x}_i(t)$ | 第$i$节板凳前把手位置 | m |
| | $\phi_i(t)$ | 第$i$节板凳方位角 | rad |

---

### 二、核心数学模型

#### 2.1 调头空间的几何界定

调头空间由盘入螺线的终点确定。设盘入螺线为阿基米德螺线：

$$\Gamma_{in}:\quad r_{in}(\theta) = a_{in}\theta, \quad \theta \in [\theta_0, \theta_A] \tag{1}$$

其中$a_{in} = p_{in}/(2\pi)$为螺线系数。盘入终点$A$的极坐标为$(r_A, \theta_A)$，其中$r_A = a_{in}\theta_A$。

**调头边界圆**定义为以原点$O$为圆心、$r_A$为半径的圆盘：

$$D = \left\{(x,y) \in \mathbb{R}^2 : x^2 + y^2 \leq R_D^2\right\}, \quad R_D = r_A = a_{in}\theta_A \tag{2}$$

盘出螺线$\Gamma_{out}$为盘入螺线关于原点的中心对称曲线（方向反转），其参数化为：

$$\Gamma_{out}:\quad r_{out}(\theta) = a_{out}\theta, \quad \theta \in [\theta_B, +\infty) \tag{3}$$

其中$a_{out} = p_{out}/(2\pi)$，且满足中心对称条件：若盘入螺线上点为$(r,\theta)$，则盘出对应点为$(r, \theta+\pi)$。

#### 2.2 双圆弧调头曲线的参数化

S形调头曲线$\Gamma_T$由两段圆弧$\Gamma_1, \Gamma_2$在切点$P$处$\mathcal{C}^1$拼接而成：

$$\Gamma_T = \Gamma_1 \cup \Gamma_2, \quad \Gamma_1 \cap \Gamma_2 = \{P\} \tag{4}$$

**前段圆弧$\Gamma_1$（右弯，曲率正）**：

$$\mathbf{r}_1(s) = \mathbf{c}_1 + R_1\begin{pmatrix} \cos\left(\phi_{1,0} + \frac{s}{R_1}\right) \\ \sin\left(\phi_{1,0} + \frac{s}{R_1}\right) \end{pmatrix}, \quad s \in [0, s_1] \tag{5}$$

其中$s_1 = R_1\alpha_1$，圆心$\mathbf{c}_1 = (c_{1x}, c_{1y})^T$，初始相位角$\phi_{1,0}$由起点约束确定。

**后段圆弧$\Gamma_2$（左弯，曲率负）**：

$$\mathbf{r}_2(s) = \mathbf{c}_2 + R_2\begin{pmatrix} \cos\left(\phi_{2,0} - \frac{s-s_1}{R_2}\right) \\ \sin\left(\phi_{2,0} - \frac{s-s_1}{R_2}\right) \end{pmatrix}, \quad s \in [s_1, s_1+s_2] \tag{6}$$

其中$s_2 = R_2\alpha_2$，负号确保曲率符号反转形成S形。

**曲率分布**：

$$\kappa(s) = \begin{cases} +\dfrac{1}{R_1}, & 0 \leq s < s_1 \\[6pt] -\dfrac{1}{R_2}, & s_1 < s \leq s_1+s_2 \end{cases} \tag{7}$$

在切点$P$处存在曲率跳变$\Delta\kappa = \frac{1}{R_1}+\frac{1}{R_2}$，这是双圆弧模型的固有特征。

#### 2.3 G¹连续性约束的数学表达

设盘入螺线在终点$A$的单位切向量为$\mathbf{T}_{in}^A$，盘出螺线在起点$B$的单位切向量为$\mathbf{T}_{out}^B$。

**起点约束（位置+切向）**：

$$\mathbf{r}_1(0) = \mathbf{r}_{in}(\theta_A) = \mathbf{r}_A \tag{8}$$

$$\mathbf{T}_1(0) = \frac{d\mathbf{r}_1}{ds}\bigg|_{s=0} = \mathbf{T}_{in}^A = \frac{1}{\sqrt{a_{in}^2+r_A^2}}\begin{pmatrix} a_{in}\cos\theta_A - r_A\sin\theta_A \\ a_{in}\sin\theta_A + r_A\cos\theta_A \end{pmatrix} \tag{9}$$

**终点约束（位置+切向）**：

$$\mathbf{r}_2(s_1+s_2) = \mathbf{r}_{out}(\theta_B) = \mathbf{r}_B \tag{10}$$

$$\mathbf{T}_2(s_1+s_2) = \mathbf{T}_{out}^B = -\mathbf{T}_{in}^A \quad \text{（方向反转）} \tag{11}$$

**内部切点约束（G¹连续）**：

$$\mathbf{r}_1(s_1) = \mathbf{r}_2(s_1) = \mathbf{r}_P \tag{12}$$

$$\mathbf{T}_1(s_1) = \mathbf{T}_2(s_1) = \mathbf{T}_P \tag{13}$$

#### 2.4 圆心位置的几何约束

由圆弧几何关系，两圆心位于切点处法线上，且满足：

$$\mathbf{c}_1 = \mathbf{r}_P - R_1\mathbf{N}_P, \quad \mathbf{c}_2 = \mathbf{r}_P + R_2\mathbf{N}_P \tag{14}$$

其中$\mathbf{N}_P$为切点$P$处单位法向量（由$\mathbf{T}_P$逆时针旋转$\pi/2$得到）。

利用起点和终点的几何关系，可得圆心位置的显式约束：

$$\|\mathbf{c}_1 - \mathbf{r}_A\| = R_1, \quad \|\mathbf{c}_2 - \mathbf{r}_B\| = R_2 \tag{15}$$

$$\|\mathbf{c}_1 - \mathbf{r}_P\| = R_1, \quad \|\mathbf{c}_2 - \mathbf{r}_P\| = R_2 \tag{16}$$

#### 2.5 边界约束：调头曲线包含于圆盘D

$$\|\mathbf{r}(s)\| \leq R_D, \quad \forall s \in [0, L_T] \tag{17}$$

对于圆弧，最严格约束通常出现在弧内点。引入辅助函数：

$$g(s) = \|\mathbf{r}(s)\|^2 - R_D^2 \leq 0, \quad \forall s \in [0, L_T] \tag{18}$$

该无限维约束可通过检验关键点（弧端点、距原点最近点）转化为有限个代数约束。

#### 2.6 运动学衔接：龙头速度恒定条件下的运动方程

龙头把手以恒定速率$v_0$沿$\Gamma$运动，弧长参数与时间关系为：

$$s(t) = v_0 t, \quad t \in [0, t_{total}] \tag{19}$$

**切向加速度与法向加速度**：

$$a_t = \frac{dv}{dt} = 0 \quad \text{（速率恒定）} \tag{20}$$

$$a_n(s) = \frac{v_0^2}{R(s)} = v_0^2|\kappa(s)| = \begin{cases} \dfrac{v_0^2}{R_1}, & s \in [0,s_1] \\[6pt] \dfrac{v_0^2}{R_2}, & s \in [s_1,L_T] \end{cases} \tag{21}$$

**角速度**：

$$\omega(s) = \frac{v_0}{R(s)} = v_0\kappa(s) \tag{22}$$

在切点$P$处，角速度发生跳变：$\Delta\omega = v_0\left(\frac{1}{R_1}+\frac{1}{R_2}\right)$，导致角加速度脉冲。

#### 2.7 链式刚体系统的位形描述

第$i$节板凳由前把手$\mathbf{x}_i$和后把手$\mathbf{x}_{i+1}$确定，其位形为：

$$\mathbf{x}_i(t) = \mathbf{r}(s_i(t)), \quad i = 0, 1, \ldots, n \tag{23}$$

其中$i=0$表示龙头，$s_i(t)$为第$i$个把手在时刻$t$的弧长坐标。

**刚性约束（把手间距固定）**：

$$\|\mathbf{x}_{i+1}(t) - \mathbf{x}_i(t)\| = L_i, \quad i = 0, 1, \ldots, n-1 \tag{24}$$

其中$L_0$为龙头板孔间距，$L_i\ (i\geq1)$为龙身板孔间距。

**板凳方位角**：

$$\phi_i(t) = \arctan2\left(y_{i+1}-y_i,\; x_{i+1}-x_i\right) \tag{25}$$

#### 2.8 无碰撞约束

每节板凳占据矩形区域，需避免重叠。采用简化圆盘约束或精确OBB（定向包围盒）约束：

**简化圆盘约束**（保守估计）：

$$\|\mathbf{x}_i(t) - \mathbf{x}_j(t)\| \geq d_{min}, \quad \forall i \neq j, \; \forall t \tag{26}$$

**精确OBB约束**：设第$i$节板凳的四个顶点为$\mathbf{v}_{i,k}(t),\ k=1,2,3,4$，则对任意两节板凳$i<j$：

$$\text{SAT}(\mathbf{v}_{i,1:4}, \mathbf{v}_{j,1:4}) = \text{true} \quad \text{（分离轴定理判定不相交）} \tag{27}$$

其中顶点由中心、方位角$\phi_i$、长度$L_i$、宽度$w$计算：

$$\mathbf{v}_{i,k} = \frac{\mathbf{x}_i+\mathbf{x}_{i+1}}{2} \pm \frac{L_i}{2}\begin{pmatrix}\cos\phi_i\\\sin\phi_i\end{pmatrix} \pm \frac{w}{2}\begin{pmatrix}-\sin\phi_i\\\cos\phi_i\end{pmatrix} \tag{28}$$

#### 2.9 优化目标函数

建立多目标优化模型，主要目标为调头时间最短，次要目标为运动平滑性：

$$\min_{\mathbf{q}} \quad J(\mathbf{q}) = w_1 J_1 + w_2 J_2 + w_3 J_3 \tag{29}$$

其中：

**调头时间**：

$$J_1 = t_{turn} = \frac{L_T}{v_0} = \frac{R_1\alpha_1 + R_2\alpha_2}{v_0} \tag{30}$$

**曲率变化总量（光滑性度量）**：

$$J_2 = \int_0^{L_T} \left(\frac{d\kappa}{ds}\right)^2 ds + \sum_{k} (\Delta\kappa_k)^2 = \left(\frac{1}{R_1}+\frac{1}{R_2}\right)^2 \tag{31}$$

对于双圆弧，曲率导数在弧内为零，仅切点处有脉冲。

**最大向心加速度（舒适性/安全性）**：

$$J_3 = \max_{s\in[0,L_T]} |a_n(s)| = v_0^2\max\left(\frac{1}{R_1}, \frac{1}{R_2}\right) \tag{32}$$

#### 2.10 完整优化问题表述

$$\boxed{\begin{aligned}
\min_{\mathbf{q}=(R_1,R_2,\alpha_1,\alpha_2,\mathbf{c}_1,\mathbf{c}_2)} \quad & J(\mathbf{q}) = w_1\frac{R_1\alpha_1+R_2\alpha_2}{v_0} + w_2\left(\frac{1}{R_1}+\frac{1}{R_2}\right)^2 + w_3 v_0^2\max\left(\frac{1}{R_1},\frac{1}{R_2}\right) \\[4pt]
\text{s.t.} \quad & \text{位置约束: } \mathbf{r}_1(0)=\mathbf{r}_A,\ \mathbf{r}_2(L_T)=\mathbf{r}_B \\[2pt]
& \text{切向约束: } \mathbf{T}_1(0)=\mathbf{T}_{in}^A,\ \mathbf{T}_2(L_T)=-\mathbf{T}_{in}^A \\[2pt]
& \text{G¹连续: } \mathbf{r}_1(s_1)=\mathbf{r}_2(s_1),\ \mathbf{T}_1(s_1)=\mathbf{T}_2(s_1) \\[2pt]
& \text{边界约束: } \|\mathbf{r}(s)\|\leq R_D,\ \forall s\in[0,L_T] \\[2pt]
& \text{曲率符号: } R_1>0,\ R_2>0,\ \alpha_1>0,\ \alpha_2>0 \\[2pt]
& \text{无碰撞: } \text{SAT}(\text{板凳}_i, \text{板凳}_j)=\text{true},\ \forall i<j,\ \forall t \\[2pt]
& \text{刚性约束: } \|\mathbf{x}_{i+1}(t)-\mathbf{x}_i(t)\|=L_i,\ \forall i,\ \forall t
\end{aligned}} \tag{33}$$

---

### 三、公式物理意义说明

| 公式编号 | 物理意义 |
|:---|:---|
| (1)-(3) | 定义了盘入/盘出螺线的极坐标方程，阿基米德螺线保证等螺距盘绕，盘出螺线通过中心对称实现方向反转 |
| (2) | 调头空间边界由盘入终点确定，形成硬性几何限制，半径$R_D$直接约束调头曲线的最大展布 |
| (5)-(6) | 双圆弧的参数方程，正负曲率组合形成S形；弧长参数化保证运动学计算的一致性 |
| (7) | 曲率的分段常数分布是双圆弧的核心特征，导致切点处存在曲率不连续 |
| (8)-(13) | G¹连续性约束组：位置连续保证轨迹不间断，切向连续保证速度方向无突变（避免速度"折返"导致的无限加速度） |
| (14)-(16) | 圆心位置的几何约束：圆心位于法线上，且到圆弧端点距离等于半径 |
| (17)-(18) | 调头曲线必须完全在允许空间内，这是可行性约束而非优化目标 |
| (19)-(22) | 恒定速率运动学：切向加速度为零，法向加速度与曲率成正比，角速度与曲率成正比；曲率跳变导致角加速度脉冲 |
| (23)-(25) | 链式刚体位形描述：每个把手在曲线上，板凳方位由前后把手确定 |
| (24) | 刚性约束体现板凳不可伸缩的本质，形成微分-代数方程系统的核心结构 |
| (26)-(28) | 无碰撞约束从简化到精确：圆盘约束计算简单但保守，OBB约束精确但计算复杂 |
| (29)-(32) | 多目标函数平衡效率（时间短）、舒适（曲率变化小）、安全（加速度小）三个维度 |
| (33) | 完整优化问题：8维决策变量，混合等式

我将为您建立龙头最大速度安全约束的完整数学模型。

---

## 板凳龙龙头最大速度安全约束数学模型

### 一、变量与参数定义

| 类别 | 符号 | 含义 | 单位/性质 |
|:---|:---|:---|:---|
| **系统参数** | $N = 223$ | 板凳总节数 | 无量纲 |
| | $N_h = 224$ | 把手总数（含首尾） | 无量纲 |
| | $L_1 = 2.86$ | 龙头板长度（把手间距） | m |
| | $L_i = 1.65$ ($i\geq 2$) | 龙身/龙尾板长度 | m |
| | $w = 0.30$ | 板凳宽度 | m |
| | $h = 0.15$ | 板凳把手直径/厚度 | m |
| **螺线参数** | $a$ | 螺线初始半径系数 | m/rad |
| | $b = p/(2\pi)$ | 螺线增长系数，$p$为螺距 | m/rad |
| | $r(\theta) = a + b\theta$ | 等距螺线方程 | m |
| **状态变量** | $\mathbf{q} = (x_1, y_1, \theta_1, \ldots, x_{224}, y_{224}, \theta_{223})^T$ | 系统构型向量 | — |
| | $s_1(t)$ | 龙头前把手弧长参数 | m |
| | $v_1 = \dot{s}_1$ | 龙头前把手速度（控制输入） | m/s |
| | $v_i$ | 第$i$个把手速度 | m/s |
| **几何变量** | $(x_i, y_i)$ | 第$i$个把手位置 | m |
| | $\varphi_i$ | 第$i$节板凳方位角 | rad |
| | $\kappa_i$ | 第$i$处轨迹曲率 | m$^{-1}$ |
| **派生变量** | $\lambda_i(\mathbf{q})$ | 速度放大系数 | 无量纲 |
| | $d_{ij}(\mathbf{q})$ | 第$i,j$节板凳最小距离 | m |
| | $v_{\max}^{(i)}$ | 第$i$节速度上限约束 | m/s |
| **目标与约束** | $v_1^*$ | 龙头最大安全速度（优化目标） | m/s |
| | $v_{\text{bound}} = 2.0$ | 各把手速度硬上限 | m/s |

---

### 二、核心数学模型

#### 2.1 螺线基准曲线与弧长参数化

板凳龙运动基于等距螺线基准曲线，其极坐标方程为：

$$r(\theta) = a + b\theta = \frac{p}{2\pi}\theta \tag{1}$$

其中设初始条件$a=0$（从原点出发），螺距$p = 0.55$ m（典型值）。弧长微元为：

$$\mathrm{d}s = \sqrt{r^2 + \left(\frac{\mathrm{d}r}{\mathrm{d}\theta}\right)^2}\,\mathrm{d}\theta = \sqrt{(b\theta)^2 + b^2}\,\mathrm{d}\theta = b\sqrt{1+\theta^2}\,\mathrm{d}\theta \tag{2}$$

弧长函数通过积分得到：

$$s(\theta) = b\int_0^{\theta}\sqrt{1+u^2}\,\mathrm{d}u = \frac{b}{2}\left[\theta\sqrt{1+\theta^2} + \ln\left(\theta+\sqrt{1+\theta^2}\right)\right] \tag{3}$$

该式建立了弧长参数$s$与极角$\theta$的一一映射，记反函数为$\theta = \Theta(s)$。

**物理意义**：式(1)-(3)构成了系统的"轨道"约束。板凳龙所有把手必须位于此螺线上，但各把手占据不同的弧长位置，形成空间分布的链式结构。弧长参数化将二维平面运动转化为一维参数控制问题。

---

#### 2.2 链式几何约束方程组

设龙头前把手位于弧长$s_1$处，对应极角$\theta_1 = \Theta(s_1)$，极径$r_1 = b\theta_1$。第$i$个把手位置由递推约束确定：

**把手位置递推关系**：

对于第$i$个把手$(x_i, y_i)$与第$i+1$个把手$(x_{i+1}, y_{i+1})$，满足固定间距约束：

$$\|\mathbf{p}_{i+1} - \mathbf{p}_i\|^2 = L_{k(i)}^2 \tag{4}$$

其中$k(i) = 1$若$i=1$，否则$k(i)=2$（区分龙头与龙身段长度），且$\mathbf{p}_i = (x_i, y_i) = (r_i\cos\theta_i, r_i\sin\theta_i)$。

展开为：

$$r_i^2 + r_{i+1}^2 - 2r_i r_{i+1}\cos(\theta_{i+1}-\theta_i) = L_{k(i)}^2 \tag{5}$$

结合$r_i = b\theta_i$，得到关于$\theta_{i+1}$的隐式方程：

$$F_i(\theta_i, \theta_{i+1}) = b^2\theta_i^2 + b^2\theta_{i+1}^2 - 2b^2\theta_i\theta_{i+1}\cos(\theta_{i+1}-\theta_i) - L_{k(i)}^2 = 0 \tag{6}$$

**物理意义**：式(4)-(6)是系统的**完整约束（Holonomic Constraints）**，表达了"刚性杆"连接的几何不可拉伸性。223节板凳通过222个此类约束耦合，使$224$个把手坐标缩减为1个自由度。

---

#### 2.3 速度传播的Jacobian映射

对约束方程(6)关于时间隐式求导。记$\omega_i = \dot{\theta}_i$，由$r_i = b\theta_i$得$\dot{r}_i = b\omega_i$。

对$F_i(\theta_i, \theta_{i+1}) = 0$求全微分：

$$\frac{\partial F_i}{\partial \theta_i}\omega_i + \frac{\partial F_i}{\partial \theta_{i+1}}\omega_{i+1} = 0 \tag{7}$$

计算偏导数：

$$\frac{\partial F_i}{\partial \theta_i} = 2b^2\theta_i - 2b^2\theta_{i+1}\cos(\theta_{i+1}-\theta_i) - 2b^2\theta_i\theta_{i+1}\sin(\theta_{i+1}-\theta_i) \tag{8}$$

$$\frac{\partial F_i}{\partial \theta_{i+1}} = 2b^2\theta_{i+1} - 2b^2\theta_i\cos(\theta_{i+1}-\theta_i) + 2b^2\theta_i\theta_{i+1}\sin(\theta_{i+1}-\theta_i) \tag{9}$$

定义**角速度传递系数**：

$$\mu_i(\mathbf{q}) = -\frac{\partial F_i/\partial \theta_i}{\partial F_i/\partial \theta_{i+1}} = \frac{\mathrm{d}\theta_{i+1}}{\mathrm{d}\theta_i} \tag{10}$$

则角速度递推：$\omega_{i+1} = \mu_i \omega_i$，进而线速度$v_i = \dot{s}_i = b\sqrt{1+\theta_i^2}\cdot\omega_i$。

**速度放大系数**定义为：

$$\lambda_i(\mathbf{q}) = \frac{v_i}{v_1} = \prod_{j=1}^{i-1}\mu_j \cdot \frac{\sqrt{1+\theta_i^2}}{\sqrt{1+\theta_1^2}} \tag{11}$$

完整的Jacobian向量：

$$\mathbf{J}(\mathbf{q}) = \left(1, \lambda_2(\mathbf{q}), \lambda_3(\mathbf{q}), \ldots, \lambda_{224}(\mathbf{q})\right)^T \in \mathbb{R}^{224} \tag{12}$$

使得：

$$\mathbf{v} = \mathbf{J}(\mathbf{q}) \cdot v_1 \tag{13}$$

**物理意义**：式(10)-(13)揭示了链式系统的核心动力学特征——**速度放大效应**。在螺线内圈（$\theta$较小处），曲率半径小，相邻把手角间距$\Delta\theta$被迫增大以维持固定杆长，导致后续把手需要更大的角速度"追赶"，形成类似鞭梢效应的非线性放大。Jacobian元素$\lambda_i$可远大于1，是限制龙头速度的关键因素。

---

#### 2.4 碰撞检测模型

每节板凳为矩形刚体，需检测非相邻板凳间的碰撞。第$i$节板凳占据区域为：

$$\mathcal{B}_i(\mathbf{q}) = \left\{(x,y) : \exists t\in[0,1], \text{ 使 } (x,y) = \mathbf{p}_i + t(\mathbf{p}_{i+1}-\mathbf{p}_i) + \mathbf{n}_i^{\perp}\cdot w/2 \cdot \xi, \xi\in[-1,1]\right\} \tag{14}$$

其中$\mathbf{n}_i^{\perp}$为垂直于板凳方向的单位向量。

**最小距离函数**：

对于非相邻节段$|i-j| \geq 2$：

$$d_{ij}(\mathbf{q}) = \min_{\mathbf{u}\in\mathcal{B}_i, \mathbf{v}\in\mathcal{B}_j}\|\mathbf{u}-\mathbf{v}\| \tag{15}$$

碰撞规避约束：

$$d_{ij}(\mathbf{q}) \geq d_{\min} = 0 \quad (\text{或考虑安全裕度 } \epsilon > 0) \tag{16}$$

**高效计算**：采用分离轴定理（SAT）或GJK算法，将矩形-矩形距离计算转化为线段投影问题。

**物理意义**：式(14)-(16)是系统的**非完整不等式约束**。与等式约束不同，碰撞约束仅在特定构型下激活（紧约束），在构型空间中形成复杂的"障碍物"区域，将一维流形切割为若干不连通的允许区间。

---

#### 2.5 龙头最大速度的优化模型

**核心优化问题**：

$$\begin{aligned}
v_1^* = \max_{v_1 > 0} \quad & v_1 \\
\text{s.t.} \quad & \text{(i) 运动学约束: } \mathbf{q}(t) \text{ 满足式(4)-(6)} \\
& \text{(ii) 速度上限约束: } |\lambda_i(\mathbf{q}(t))| \cdot v_1 \leq v_{\max}^{(i)}, \quad \forall i, \forall t \tag{17}\\
& \text{(iii) 碰撞规避约束: } d_{ij}(\mathbf{q}(t)) \geq 0, \quad \forall |i-j|\geq 2, \forall t \\
& \text{(iv) 初始条件: } \mathbf{q}(0) = \mathbf{q}_0
\end{aligned}$$

**关键转化——准静态假设**：

由于螺线运动具有缓慢变化的拟稳态特征，可将时间参数消去，转化为纯几何约束问题。对于给定龙头弧长位置$s_1$，求解：

$$v_1^{\max}(s_1) = \min\left\{ \min_{i}\frac{v_{\max}^{(i)}}{|\lambda_i(\mathbf{q}(s_1))|}, \quad v_1^{\text{collision}}(s_1) \right\} \tag{18}$$

其中$v_1^{\text{collision}}(s_1)$为碰撞约束隐式定义的临界速度（若当前构型已处于碰撞边界，则$v_1^{\text{collision}}=0$）。

全局最大安全速度：

$$v_1^* = \min_{s_1 \in [s_{\min}, s_{\max}]} v_1^{\max}(s_1) \tag{19}$$

**物理意义**：式(17)-(19)构成了**瓶颈分析（Bottleneck Analysis）**。龙头速度受两类瓶颈制约：(a)速度放大导致的某节速度超限；(b)几何自相交导致的碰撞。全局最优解由最严格的局部约束决定，体现了"链条强度取决于最弱环节"的原理。

---

#### 2.6 碰撞临界速度的局部线性化

当系统接近碰撞构型$\mathbf{q}^*$（即某$d_{ij}=0$），设相对速度在碰撞法向的投影为：

$$\dot{d}_{ij} = \mathbf{n}_{ij}^T \cdot (\mathbf{v}_j^{\text{eff}} - \mathbf{v}_i^{\text{eff}}) \tag{20}$$

其中$\mathbf{v}_i^{\text{eff}}$为第$i$节板凳碰撞点的有效速度，与把手速度通过刚体运动学关联：

$$\mathbf{v}_i^{\text{eff}} = \mathbf{v}_{\text{handle},i} + \boldsymbol{\omega}_i \times \mathbf{r}_{i,\text{eff}} \tag{21}$$

碰撞避免要求$\dot{d}_{ij} \geq 0$（分离趋势），即：

$$\mathbf{n}_{ij}^T \cdot \left[\sum_{k}\frac{\partial \mathbf{v}_i^{\text{eff}}}{\partial v_k}\lambda_k - \sum_{k}\frac{\partial \mathbf{v}_j^{\text{eff}}}{\partial v_k}\lambda_k\right] v_1 \geq 0 \tag{22}$$

若当前处于临界碰撞（$d_{ij}=0$），则要求$v_1 \leq 0$或重新规划路径，表明该构型不可行。

---

### 三、模型假设与适用范围

| 编号 | 假设内容 | 数学表达 | 合理性分析 |
|:---|:---|:---|:---|
| **A1** | 板凳为理想刚体，无弹性变形 | $L_i \equiv \text{const}$ | 木质板凳刚度足够，变形远小于几何间隙 |
| **A2** | 把手为点连接，忽略尺寸 | 式(4)为等式约束 | 把手直径$h=0.15$m相对于$L_i$可忽略，或修正$L_i^{\text{eff}}=L_i-h$ |
| **A3** | 平面运动，忽略三维起伏 | $z \equiv 0$ | 舞龙场地平整，垂直运动可忽略 |
| **A4** | 无滑动，把手严格沿螺线 | $\mathbf{p}_i \in \Gamma_{\text{spiral}}$ | 实际存在操作误差，模型给出理论上限 |
| **A5** | 准静态速度传播，忽略惯性 | 式(18)忽略$\dot{\mathbf{J}}$项 | 龙头速度$v_1\sim 1$m/s，系统尺度$\sim 10$m，特征频率低，惯性效应次要 |
| **A6** | 各把手速度硬上限相同 | $v_{\max}^{(i)} \equiv 2.0$ m/s | 基于人体工程学约束，可推广为节段相关函数 |
| **A7** | 碰撞仅考虑非相邻节段 | $|i-j|\geq 2$ | 相邻节段由铰接连接，距离恒为$L_i$，无碰撞可能 |
| **A8** | 螺线参数恒定，无路径切换 | $b = \text{const}$ | 调头问题需分段模型，此处专注单螺线阶段 |

---

### 四、模型求解策略

该模型的数值求解面临**高维隐式约束**与**非光滑碰撞检测**的挑战，建议采用以下策略：

1. **构型空间离散化**：在弧长参数$s_1 \in [0, S_{\max}]$上取网格点
2. **并行递推求解**：对每个$s_1^{(k)}$，并行求解非线性方程组(6)得全部$\theta_i$
3. **Jacobian计算**：数值差分或解析公式(8)-(11)计算$\lambda_i$
4. **碰撞检测加速**：空间哈希或BVH树加速$O(N^2)$距离计算
5. **瓶颈定位**：记录所有约束的活跃集，识别关键限制节段

该模型完整刻画了"龙头速度输入—链式几何传播—多约束耦合—安全上限反解"的物理机制，为板凳龙表演的参数优化与安全控制提供了严谨的理论框架。