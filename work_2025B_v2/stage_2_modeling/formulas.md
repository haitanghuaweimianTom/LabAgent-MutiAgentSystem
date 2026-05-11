## 双光束干涉光谱测量外延层厚度的数学模型

### 一、模型变量与参数定义

| 类别 | 符号 | 含义 | 单位 | 取值范围/备注 |
|:---|:---|:---|:---|:---|
| **基本物理常数** | $c$ | 真空光速 | m/s | $2.998 \times 10^8$ |
| | $h$ | 普朗克常数 | J·s | $6.626 \times 10^{-34}$ |
| **入射光参数** | $\lambda$ | 真空波长 | μm | 红外波段 2.5–25（中红外）|
| | $\tilde{\nu}$ | 波数 | cm⁻¹ | $\tilde{\nu} = 10^4/\lambda$（$\lambda$ 单位为 μm）|
| | $\theta_0$ | 空气中入射角 | rad | 常取 0（正入射）或 $\theta_0 \in [0, \pi/6]$ |
| **材料光学参数** | $n_0$ | 空气折射率 | — | $n_0 = 1$ |
| | $n_1(\lambda, N_d)$ | 外延层折射率（色散+掺杂依赖）| — | SiC: 2.55–2.75 |
| | $n_2(\lambda)$ | 衬底折射率（色散）| — | SiC衬底: 2.60–2.80 |
| | $N_d(z)$ | 掺杂载流子浓度 | cm⁻³ | $10^{15}$–$10^{19}$ |
| | $\Delta n = n_2 - n_1$ | 折射率对比度 | — | SiC典型值: $10^{-3}$–$10^{-2}$ |
| **结构几何参数** | $d$ | **外延层厚度（待求）**| μm | 典型值: 5–100 μm |
| | $z$ | 外延层深度坐标 | μm | $z \in [0, d]$，表面为原点 |
| **派生变量** | $\theta_1(\lambda)$ | 外延层中折射角 | rad | 由斯涅尔定律确定 |
| | $\beta(\lambda)$ | 单层相位厚度 | rad | $\beta = 2\pi n_1 d \cos\theta_1 / \lambda$ |
| | $\phi_{01}, \phi_{12}$ | 界面反射相位跃变 | rad | 含于 $r_{01}, r_{12}$ 的复角 |
| **反射系数** | $r_{01}, r_{12}$ | 振幅反射系数（复数）| — | 含模与相位信息 |
| | $R_{01}, R_{12}$ | 强度反射率 | — | $R = \|r\|^2$ |
| | $\rho_{01}, \rho_{12}$ | 振幅反射系数模 | — | $\rho = \|r\|$ |
| **测量量** | $R_{meas}(\lambda)$ | 实测反射率光谱 | — | 需归一化至参考镜面 |

---

### 二、双光束干涉的核心数学模型

#### 2.1 斯涅尔定律与传播角度

光从空气（$n_0=1$）入射至外延层-衬底结构，各介质中的传播方向满足：

$$\sin\theta_0 = n_1(\lambda)\sin\theta_1 = n_2(\lambda)\sin\theta_2 \tag{1}$$

对于红外干涉测量常用的正入射或近正入射条件（$\theta_0 \leq 15°$），有近似 $\cos\theta_1 \approx 1 - \sin^2\theta_0/(2n_1^2)$。定义有效光学厚度时引入倾斜因子：

$$\boxed{\gamma(\lambda, \theta_0) = \sqrt{n_1^2(\lambda) - \sin^2\theta_0}} \tag{2}$$

则相位厚度可统一写为 $\beta = 2\pi d \gamma / \lambda$，正入射时退化为 $\gamma = n_1$。

#### 2.2 菲涅耳振幅反射系数的完整表述

界面处的复振幅反射系数由电磁场边值条件严格导出。对于非磁性介质（$\mu_r = 1$），s偏振（TE）与p偏振（TM）的通用形式为：

$$r_{jk}^{(s)} = \frac{\gamma_j - \gamma_k}{\gamma_j + \gamma_k}, \quad r_{jk}^{(p)} = \frac{n_k^2\gamma_j - n_j^2\gamma_k}{n_k^2\gamma_j + n_j^2\gamma_k} \tag{3}$$

其中 $\gamma_j = \sqrt{n_j^2 - \sin^2\theta_0}$（正入射时 $\gamma_j = n_j$）。对于SiC外延层-衬底系统，关键特征在于 $n_1 \approx n_2$ 导致弱反射近似成立。

**正入射情形下的核心公式**（本模型主要工作条件）：

$$\boxed{r_{01} = \frac{1 - n_1}{1 + n_1}, \quad r_{12} = \frac{n_1 - n_2}{n_1 + n_2}} \tag{4}$$

**相位特性分析**：由于SiC外延层与衬底均为高折射率介质（$n > 2.5$），$r_{01} < 0$（光从光疏到光密介质，反射相位跃变 $\pi$）；而 $r_{12}$ 的符号取决于掺杂导致的折射率梯度——通常外延层轻掺杂、衬底重掺杂，故 $n_2 > n_1$，$r_{12} < 0$。因此：

$$\text{sgn}(r_{01} \cdot r_{12}) = (+1) \quad \Rightarrow \quad \text{干涉项系数为负} \tag{5}$$

这一符号特征决定了干涉条纹的极值条件，将在2.4节详述。

#### 2.3 双光束干涉反射率的严格推导

考虑图1所示的物理过程：入射光振幅 $E_0$ 在空气-外延层界面（界面0-1）部分反射形成光束1，透射部分在外延层中传播、经外延层-衬底界面（界面1-2）反射后返回、再透射出表面形成光束2。两束光的复振幅分别为：

$$\tilde{E}_1 = r_{01} E_0 \tag{6}$$

$$\tilde{E}_2 = t_{01} \cdot r_{12} \cdot t_{10} \cdot e^{-i2\beta} \cdot E_0 \tag{7}$$

其中 $t_{01}t_{10} = 1 - r_{01}^2 = 1 - R_{01}$（斯托克斯倒逆关系，无吸收情形），往返相位因子：

$$\boxed{\beta(\lambda) = \frac{2\pi n_1(\lambda) d \cos\theta_1}{\lambda} = \frac{2\pi d \gamma(\lambda)}{\lambda}} \tag{8}$$

总反射光场为 $\tilde{E}_R = \tilde{E}_1 + \tilde{E}_2$，强度反射率 $R = |\tilde{E}_R/E_0|^2$。严格表达式为：

$$\boxed{R(\lambda) = \frac{R_{01} + R_{12} + 2\sqrt{R_{01}R_{12}}\cos(2\beta + \phi_{01} - \phi_{12})}{1 + R_{01}R_{12} + 2\sqrt{R_{01}R_{12}}\cos(2\beta + \phi_{01} - \phi_{12})}} \tag{9}$$

其中 $\phi_{jk} = \arg(r_{jk})$。对于透明介质且 $n_j$ 均为实数的情形，$r_{01}, r_{12}$ 为实数，$\phi_{01} = \pi$（因 $r_{01}<0$），$\phi_{12} = \pi$（因 $r_{12}<0$），故 $\phi_{01} - \phi_{12} = 0$。

**弱反射近似**：SiC系统的典型参数为 $R_{01} \approx 0.18$（空气-SiC），$R_{12} \approx 10^{-5}$–$10^{-6}$（外延层-衬底折射率差 $\Delta n/n \sim 10^{-3}$）。由于 $R_{01}R_{12} \ll 1$，分母近似为1，分子中 $\sqrt{R_{01}R_{12}} = |r_{01}r_{12}|$，且 $r_{01}r_{12} > 0$（两负相乘），但标准展开形式需注意：

$$R \approx |r_{01}|^2 + |r_{12}|^2 + 2r_{01}r_{12}\cos(2\beta) \tag{10}$$

由于 $r_{01} < 0$, $r_{12} < 0$，有 $r_{01}r_{12} > 0$，然而公式(10)中显式写出 $2r_{01}r_{12}\cos(2\beta)$ 时，若采用 $r_{12}$ 的负值直接代入，则干涉项为负。为消除符号混淆，采用模-相位分离表示：

$$\boxed{R(\lambda) \approx R_{01} + R_{12} + 2|r_{01}r_{12}|\cos(2\beta + \pi) = R_{01} + R_{12} - 2|r_{01}r_{12}|\cos(2\beta)} \tag{11}$$

或等价地写为：

$$\boxed{R(\lambda) \approx R_{01} + R_{12} + 2r_{01}r_{12}\cos(2\beta), \quad r_{01}r_{12} < 0} \tag{11a}$$

此处的关键物理含义：当两界面反射系数同号时，干涉极小对应相位厚度 $\beta = m\pi$（$m$ 为整数），即光程差为半波长的整数倍时相消干涉。

#### 2.4 干涉极值条件与厚度-波长关系

由式(11)，反射率极值由 $\cos(2\beta)$ 的极值决定：

- **反射极小**（相消干涉）：$\cos(2\beta) = +1$，即 $2\beta = 2m\pi$，$m = 0, 1, 2, \ldots$

$$\boxed{2n_1(\lambda_m^{min})d = m\lambda_m^{min}} \tag{12}$$

- **反射极大**（相长干涉）：$\cos(2\beta) = -1$，即 $2\beta = (2m+1)\pi$

$$\boxed{2n_1(\lambda_m^{max})d = \left(m+\frac{1}{2}\right)\lambda_m^{max}} \tag{13}$$

**干涉级次的确定**：对于SiC外延层（$d \sim 10$ μm，$n_1 \sim 2.6$），在 $\lambda = 10$ μm 处的相位厚度 $\beta \approx 2\pi \times 2.6 \times 10 / 10 = 16.3\pi$，即干涉级次 $m \sim 16$。相邻极值的波长间隔（自由光谱范围）：

$$\Delta\lambda \approx \frac{\lambda^2}{2n_1 d} \tag{14}$$

对于 $d = 10$ μm，$\lambda = 10$ μm，$\Delta\lambda \approx 0.38$ μm，在红外光谱仪分辨率范围内可分辨。

#### 2.5 色散模型与折射率-波长-掺杂关系

SiC的折射率色散需采用适用于宽红外波段的解析模型。基于经典振子理论的Sellmeier方程扩展形式：

$$\boxed{n^2(\lambda) = 1 + \sum_{j=1}^{3}\frac{S_j \lambda^2}{\lambda^2 - \lambda_j^2} + \Delta n_{fc}(\lambda, N_d)} \tag{15}$$

其中 $S_j$ 为振子强度，$\lambda_j$ 为共振波长。对于4H-SiC，文献拟合参数为：

| 振子项 | $S_j$ | $\lambda_j$ (μm) |
|:---|:---|:---|
| $j=1$ | 5.5914 | 0.1631 |
| $j=2$ | 1.9358 | 0.1760 |
| $j=3$ | 0.0001 | 10.0000 |

自由载流子贡献（Drude模型修正）：

$$\Delta n_{fc}(\lambda, N_d) = -\frac{e^2\lambda^2 N_d}{8\pi^2\varepsilon_0 c^2 n m^*} \tag{16}$$

其中 $m^*$ 为载流子有效质量（4H-SiC电子有效质量 $m_e^* \approx 0.29m_0$），$N_d$ 为掺杂浓度。该贡献导致重掺杂衬底折射率 $n_2$ 略低于轻掺杂外延层 $n_1$，形成 $\Delta n = n_2 - n_1 < 0$ 的负对比度，即 $r_{12} < 0$。

**外延层内的掺杂梯度效应**：实际外延生长过程中，掺杂浓度沿深度方向存在分布 $N_d(z)$，导致折射率分布 $n(z,\lambda) = n_0(\lambda) + \Delta n_{fc}(\lambda, N_d(z))$。对于线性梯度近似：

$$N_d(z) = N_{d0} + (N_{dd} - N_{d0})\frac{z}{d} \tag{17}$$

此时相位厚度需修正为积分形式：

$$\beta_{eff} = \frac{2\pi}{\lambda}\int_0^d n(z,\lambda)\cos\theta(z)\, dz \tag{18}$$

其中 $\theta(z)$ 由局部斯涅尔定律 $n(z)\sin\theta(z) = \sin\theta_0$ 确定。在WKB近似下，有效光学厚度为：

$$\boxed{d_{eff} = \int_0^d \sqrt{n^2(z) - \sin^2\theta_0}\, dz \Big/ \sqrt{\bar{n}^2 - \sin^2\theta_0}} \tag{19}$$

其中 $\bar{n}$ 为平均折射率。当梯度较小时（$|\Delta n_{fc}|/n \ll 1$），可展开至一阶：

$$d_{eff} \approx d\left[1 + \frac{1}{2n_0}\left(\frac{1}{d}\int_0^d \Delta n_{fc}(z)\, dz - \Delta n_{fc}(d/2)\right)\right] \tag{20}$$

对于线性梯度，积分平均等于中点值，故 $d_{eff} \approx d$，即一阶修正消失。实际测量中需考虑二阶效应或采用数值积分。

---

### 三、低对比度干涉信号的增强方法

SiC外延层-衬底系统的折射率对比度极低（$\Delta n/n \sim 10^{-3}$），导致干涉条纹对比度（可见度）：

$$V = \frac{R_{max} - R_{min}}{R_{max} + R_{min}} \approx \frac{2\sqrt{R_{01}R_{12}}}{R_{01} + R_{12}} \approx 2\sqrt{\frac{R_{12}}{R_{01}}} \sim 10^{-2} \tag{21}$$

即条纹调制深度仅约1%，远低于常规薄膜干涉测量。需采用特殊信号处理技术：

#### 3.1 差分光谱技术

测量同一晶圆片在外延生长前后的反射光谱 $R_{post}(\lambda)$ 和 $R_{pre}(\lambda)$，差分信号消除系统背景：

$$\Delta R(\lambda) = R_{post}(\lambda) - R_{pre}(\lambda) \approx R_{12} - 2|r_{01}r_{12}|\cos(2\beta) \tag{22}$$

此时干涉项相对幅度提升至 $\sim 100\%$，但需保证两次测量的绝对角度一致性（误差 $< 0.1°$）。

#### 3.2 偏振调制技术

利用斜入射时s偏振与p偏振反射系数的差异，定义偏振差分反射率：

$$\Delta R_{sp}(\lambda) = R^{(s)}(\lambda) - R^{(p)}(\lambda) \tag{23}$$

对于SiC的弱吸收区，该差分信号对界面敏感且抑制了共同模式噪声。具体地，由式(3)：

$$r_{01}^{(s)} - r_{01}^{(p)} = \frac{2\sin^2\theta_0(n_1^2-1)\cos\theta_0}{(n_1\cos\theta_0+\cos\theta_1)(n_1\cos\theta_1+\cos\theta_0)} \tag{24}$$

在布儒斯特角附近（$\theta_0 \approx \arctan n_1 \approx 69°$），$r_{01}^{(p)} \to 0$，此时p偏振的参考反射光极弱，s偏振的干涉信号相对增强。

#### 3.3 角度分辨测量与傅里叶变换增强

在固定波长 $\lambda_0$ 下扫描入射角 $\theta_0$，记录 $R(\theta_0)$。由式(8)，$\beta$ 随 $\theta_0$ 变化：

$$\beta(\theta_0) = \frac{2\pi d}{\lambda_0}\sqrt{n_1^2 - \sin^2\theta_0} \tag{25}$$

对角度扫描数据进行余弦变换：

$$\mathcal{F}(Q) = \int_{\theta_{min}}^{\theta_{max}} [R(\theta_0) - \bar{R}] \exp(iQ\beta(\theta_0))\, d\theta_

我将基于您的分析，建立碳化硅外延层厚度反演的完整数学模型。

---

# 碳化硅外延层厚度反演数学模型

## 一、变量与参数定义

| 符号 | 类型 | 物理意义 | 单位 |
|:---|:---|:---|:---|
| $d$ | 待求变量 | 外延层厚度 | $\mu\text{m}$ |
| $n_0$ | 参数 | 入射介质折射率（空气/真空） | 1 |
| $n_1(\lambda)$ | 函数参数 | 外延层折射率（随波长变化） | — |
| $n_2$ | 参数 | 衬底折射率 | — |
| $n_3$ | 参数 | 背底介质折射率 | — |
| $\theta_0$ | 参数 | 入射角 | rad |
| $\theta_1$ | 导出变量 | 外延层内折射角 | rad |
| $\lambda_k$ | 测量数据 | 第$k$个干涉极值波长 | $\mu\text{m}$ |
| $\tilde{\nu}_k = 1/\lambda_k$ | 导出数据 | 第$k$个干涉极值波数 | $\mu\text{m}^{-1}$ |
| $m_k$ | 整数变量 | 第$k$个极值干涉级次 | — |
| $R(\lambda)$ | 测量光谱 | 反射率光谱 | — |
| $\phi$ | 相位变量 | 两光束相位差 | rad |
| $\tilde{d}$ | 导出变量 | 有效光学厚度 | $\mu\text{m}$ |
| $A, B, C, D$ | 拟合参数 | Sellmeier色散模型系数 | 各异 |
| $a_0, a_1, a_2$ | 拟合参数 | Cauchy色散模型系数 | 各异 |

---

## 二、核心数学模型

### 2.1 双光束干涉基础模型

基于薄膜光学中的双光束干涉近似，考虑外延层上、下表面反射光的相干叠加。设入射光从折射率$n_0$介质以角$\theta_0$入射，经Snell定律折射进入外延层：

$$\begin{equation}
n_0\sin\theta_0 = n_1\sin\theta_1
\end{equation}$$

两束反射光的光程差为：
$$\begin{equation}
\Delta L = 2n_1 d \cos\theta_1
\end{equation}$$

由于上表面（$n_0 < n_1$）反射存在半波损失，下表面（$n_1 > n_2$，SiC衬底）反射亦存在半波损失，两束光相位关系需仔细分析。**当$n_0 < n_1 > n_2$时**，两束反射光均经历或均不经历半波损失，净效果为无额外$\pi$相位差；**当$n_0 < n_1 < n_2$时**，仅上表面有半波损失，产生额外$\pi$相位差。

对于SiC外延层（$n_1 \approx 2.6$）在SiC衬底（$n_2 \approx 2.6$）上的情形，若外延层与衬底折射率接近，需考虑具体数值关系。一般情形下，**相长干涉条件**为：

$$\begin{equation}
2n_1(\tilde{\nu}_k) d \cos\theta_1 = \left(m_k + \frac{1}{2}\right)\lambda_k = \frac{m_k + \frac{1}{2}}{\tilde{\nu}_k}, \quad m_k = 0, 1, 2, \ldots
\end{equation}$$

**相消干涉条件**为：
$$\begin{equation}
2n_1(\tilde{\nu}_k) d \cos\theta_1 = m_k \lambda_k = \frac{m_k}{\tilde{\nu}_k}, \quad m_k = 1, 2, 3, \ldots
\end{equation}$$

公式(3)的物理意义：光在薄膜内往返的几何光程$2n_1 d \cos\theta_1$（考虑折射角修正）等于半整数波长时，两束反射光因半波损失的补偿作用而同相叠加，形成反射光谱中的极大值（或透射光谱中的极小值）。该方程建立了**四个未知量**（$d$, $n_1$, $m_k$, $\lambda_k$）之间的约束关系，构成反演问题的核心方程。

### 2.2 波数域线性化模型

将式(3)改写为波数域形式：
$$\begin{equation}
2n_1(\tilde{\nu}_k) d \cos\theta_1 \cdot \tilde{\nu}_k = m_k + \frac{1}{2}
\end{equation}$$

**无色散近似**（$n_1$为常数）：定义有效光学厚度$\tilde{d} = 2n_1 d \cos\theta_1$，则式(5)简化为：
$$\begin{equation}
\tilde{d} \cdot \tilde{\nu}_k = m_k + \frac{1}{2}
\end{equation}$$

此式表明，在波数域中相邻极值点的间距为常数：
$$\begin{equation}
\Delta\tilde{\nu} = \tilde{\nu}_{k+1} - \tilde{\nu}_k = \frac{1}{\tilde{d}} = \frac{1}{2n_1 d \cos\theta_1}
\end{equation}$$

该线性关系为厚度初值估计提供了直接途径：通过测量光谱极值点位置的统计平均，即可快速估算有效光学厚度，进而获得厚度初值。

### 2.3 折射率色散模型

碳化硅外延层的折射率具有显著的波长依赖性，必须引入色散模型以确保厚度反演精度。对于红外波段（$2\sim20\,\mu\text{m}$），采用两种等效模型：

**Sellmeier模型**（物理基础明确，适用于宽波段）：
$$\begin{equation}
n_1^2(\lambda) = A + \frac{B\lambda^2}{\lambda^2 - C} + \frac{D\lambda^2}{\lambda^2 - E}
\end{equation}$$

其中$A, B, C, D, E$为拟合参数，$C, E$对应材料的本征吸收波长。

**Cauchy模型**（计算简便，适用于正常色散区）：
$$\begin{equation}
n_1(\lambda) = a_0 + \frac{a_1}{\lambda^2} + \frac{a_2}{\lambda^4}
\end{equation}$$

对于掺杂SiC外延层，折射率还受载流子浓度$N$影响，需引入Drude修正：
$$\begin{equation}
n_1^2(\lambda, N) = n_{0}^2(\lambda) - \frac{e^2 N \lambda^2}{4\pi^2 c^2 \varepsilon_0 m^*}
\end{equation}$$

其中$n_{0}(\lambda)$为本征折射率，$m^*$为载流子有效质量，$c$为真空光速，$e$为电子电荷，$\varepsilon_0$为真空介电常数。该修正项在长波波段（自由载流子吸收区）尤为重要，导致折射率随波长增加而降低的异常色散行为。

### 2.4 斜入射修正与偏振效应

实际测量中，入射光通常为斜入射（$\theta_0 \neq 0$），需区分$s$偏振（电场垂直于入射面）与$p$偏振（电场平行于入射面）的有效折射率：

$$\begin{equation}
n_{1,s}^{\text{eff}} = n_1 \cos\theta_1, \quad n_{1,p}^{\text{eff}} = \frac{n_1}{\cos\theta_1}
\end{equation}$$

对应的干涉条件修正为：
$$\begin{equation}
2d \cdot n_{1,\sigma}^{\text{eff}} = \left(m_k + \frac{1}{2}\right)\lambda_k, \quad \sigma \in \{s, p\}
\end{equation}$$

对于非偏振光或混合偏振测量，需对两种偏振态的反射率进行强度加权平均，或明确标注测量配置以消除系统误差。

---

## 三、厚度反演算法设计

### 3.1 算法整体框架

基于上述模型，设计**迭代优化反演算法**，核心思想为：利用极值点波数与干涉级次的线性关系确定厚度初值，再通过非线性最小二乘优化精化厚度与色散参数。算法流程如下：

**步骤1：光谱预处理与极值提取**

对原始反射光谱$R(\lambda)$进行Savitzky-Golay平滑滤波，消除高频噪声；采用基于连续小波变换或局部极值搜索算法，自动识别干涉极值点$\{(\lambda_k, R_k)\}_{k=1}^{K}$，其中$K$为检测到的极值点总数。极值点判据为：
$$\begin{equation}
\frac{\text{d}R}{\text{d}\lambda}\bigg|_{\lambda=\lambda_k} = 0, \quad \frac{\text{d}^2R}{\text{d}\lambda^2}\bigg|_{\lambda=\lambda_k} \cdot (-1)^k > 0
\end{equation}$$

其中$k$的奇偶性对应极大值与极小值的交替分布。

**步骤2：干涉级次判定与厚度初值估计**

假设无色散近似成立，将极值点按波数排序后，相邻极值点满足：
$$\begin{equation}
\tilde{\nu}_{k+1} - \tilde{\nu}_k \approx \frac{1}{2n_1 d \cos\theta_1}
\end{equation}$$

由于干涉级次$m_k$为未知整数，需解决**级次模糊问题**。利用相邻极值点间距的稳定性判据：计算所有相邻间距的标准差，选取使变异系数最小的整数平移量$\Delta m$，确定各点级次。厚度初值估计为：
$$\begin{equation}
\hat{d}_0 = \frac{1}{2n_1^{(0)} \cos\theta_1 \cdot \langle\Delta\tilde{\nu}\rangle}
\end{equation}$$

其中$n_1^{(0)}$为折射率先验估计值（可取SiC本征折射率$n_1 \approx 2.55$），$\langle\Delta\tilde{\nu}\rangle$为相邻极值点波数差的平均值。

**步骤3：联合优化反演**

建立以厚度$d$和色散参数$\boldsymbol{\beta} = (A, B, C, \ldots)^T$为优化变量的非线性最小二乘目标函数：
$$\begin{equation}
\min_{d, \boldsymbol{\beta}} \sum_{k=1}^{K} \left[2n_1(\lambda_k; \boldsymbol{\beta}) d \cos\theta_1 - \frac{m_k + \frac{1}{2}}{\tilde{\nu}_k}\right]^2 + \mu \|\boldsymbol{\beta} - \boldsymbol{\beta}_0\|^2
\end{equation}$$

其中第二项为正则化约束，$\boldsymbol{\beta}_0$为文献报道的SiC色散参数先验值，$\mu$为正则化系数，用于平衡拟合优度与参数物理合理性。

采用Levenberg-Marquardt算法求解该非线性优化问题，迭代更新规则为：
$$\begin{equation}
\begin{bmatrix} d \\ \boldsymbol{\beta} \end{bmatrix}^{(j+1)} = \begin{bmatrix} d \\ \boldsymbol{\beta} \end{bmatrix}^{(j)} + \left(\mathbf{J}^T\mathbf{J} + \lambda^{(j)}\text{diag}(\mathbf{J}^T\mathbf{J})\right)^{-1}\mathbf{J}^T\mathbf{r}
\end{equation}$$

其中$\mathbf{J}$为残差向量$\mathbf{r}$关于优化参数的Jacobian矩阵，$\lambda^{(j)}$为自适应阻尼因子。

**步骤4：模型验证与不确定性量化**

收敛后，计算拟合残差的标准差$\sigma_r$和决定系数$R^2$；通过Jacobian矩阵的奇异值分解，估计参数协方差矩阵：
$$\begin{equation}
\text{Cov}\begin{bmatrix} \hat{d} \\ \hat{\boldsymbol{\beta}} \end{bmatrix} \approx \sigma_r^2 \left(\mathbf{J}^T\mathbf{J}\right)^{-1}\bigg|_{(d, \boldsymbol{\beta}) = (\hat{d}, \hat{\boldsymbol{\beta}})}
\end{equation}$$

厚度测量的标准不确定度为：
$$\begin{equation}
u(\hat{d}) = \sqrt{[\text{Cov}]_{11}}
\end{equation}$$

相对不确定度$u(\hat{d})/\hat{d}$作为结果可靠性的量化指标。

### 3.2 针对附件数据的算法适配

附件1与附件2提供不同入射角（或不同样品）的碳化硅晶圆片光谱数据。算法需根据实际数据特征进行适配：

- **数据格式解析**：提取波长-反射率数据对，统一转换为波数域处理；
- **基线校正**：若光谱存在倾斜基线（源于仪器响应或散射背景），采用多项式拟合或自适应迭代加权惩罚最小二乘（airPLS）进行基线扣除；
- **极值点筛选**：设置信噪比阈值，剔除伪极值点；对密集采样数据，可采用聚类算法合并过密极值；
- **多光谱联合反演**：若附件1、2为同一样品的不同入射角测量，联合建立目标函数，增强参数估计的稳健性：
$$\begin{equation}
\min_{d, \boldsymbol{\beta}} \sum_{i=1}^{2}\sum_{k=1}^{K_i} w_i \left[2n_1(\lambda_{k,i}; \boldsymbol{\beta}) d \cos\theta_{1,i} - \frac{m_{k,i} + \frac{1}{2}}{\tilde{\nu}_{k,i}}\right]^2
\end{equation}$$

其中$w_i$为各数据集的权重，反比于其测量方差。

---

## 四、多光束干涉效应分析

### 4.1 多光束干涉的物理机制

当外延层界面反射率较高或界面质量优异时，光波在薄膜内产生多次反射与透射，形成多光束干涉。第$j$束反射光的振幅为：
$$\begin{equation}
r_j = t_{01}t_{10}r_{12}^{2j-1} e^{i(j-1)\phi}, \quad j = 1, 2, 3, \ldots
\end{equation}$$

其中$t_{01}, t_{10}$为界面透射系数，$r_{12}$为外延层-衬底界面反射系数，$\phi = 4\pi n_1 d \cos\theta_1 / \lambda$为相邻光束的相位差。

总反射率为无穷等比级数求和：
$$\begin{equation}
R_{\text{multi}} = \left|\frac{r_{01} + r_{12}e^{i\phi}}{1 + r_{01}r_{12}e^{i\phi}}\right|^2
\end{equation}$$

此即Airy公式，其中$r_{01} = (n_0 - n_1)/(n_0 + n_1)$为空气-外延层界面反射系数。

### 4.2 多光束干涉的必要条件

多光束干涉显著影响光谱形态的必要条件为：

**条件一：高反射率界面**
$$\begin{equation}
|r_{01}r_{12}| \gtrsim 0.2
\end{equation}$$

对于SiC外延层，$n_1 \approx 2.6, n_0 = 1$，则$|r_{01}| \approx 0.44$；若外延层与衬底折射率差异$|n_1 - n_2|$较小（同质外延情形），$|r_{12}|$很小，多光束效应被抑制。

**条件二：相干长度匹配**
光源相干长度$L_c \gg 2n_1 d/\cos\theta_1$，确保各次反射光保持相位关联。傅里叶变换红外光谱仪（FTIR）通常满足此条件。

**条件三：界面平整度**
界面粗糙度$\sigma_h \ll \lambda/4$，避免漫散射破坏相干叠加。

### 4.3 多光束干涉对厚度计算的影响

双光束近似下，极值点位置由$\phi = (2m+1)\pi$（极大值）或$\phi = 2m\pi$（极小值）确定。多光束干涉引入Airy函数的精细结构：

$$\begin{equation}
R_{\text{multi}} = \frac{R_{01} + R_{12} + 2\sqrt{R_{01}R_{12}}\cos\phi}{1 + R_{01}R_{12} + 2\sqrt{R_{01}R_{12}}\cos\phi}
\end{equation}$$

其中$R_{01} = r_{01}^2, R_{12} = r_{12}^2$。极值点位置偏移量为：
$$\begin{equation}
\delta\phi \approx -\frac{2\sqrt{R_{01}R_{12}}(1-R_{01})(1-R_{12})}{1-R_{01}R_{12}} \sin\phi
\end{equation}$$

该偏移导致：
1. **峰位偏移**：极值波长系统性偏离双光束预测值，直接套用双光束模型将引入厚度计算偏差；
2. **峰形不对称**：Airy函数的极值点不再严格等间距，破坏波数域线性关系；
3. **衬度变化**：条纹可见度受$F = 4R_{01}R_{12}/(1-R_{01}R_{12})^2$（精细度系数）调制。

### 4.4 多光束干涉的判别与消除

**判别方法**：计算实测光谱的峰形参数——半高全宽（FWHM）与峰底宽之比。双光束近似下该比值约为0.5；多光束干涉时比值增大，且随精细度$F$增加趋近于1。

**消除策略一：直接采用多光束模型**

将反演目标函数修正为Airy函数形式：
$$\begin{equation}
\min_{d, \boldsymbol{\beta}} \sum_{k=1}^{K} \left[R_{\text{multi}}(\lambda_k; d, \boldsymbol{\beta})

## 多光束干涉薄膜厚度测量数学模型

### 一、变量与参数定义

| 类别 | 符号 | 定义 | 单位 | 备注 |
|:---|:---|:---|:---|:---|
| **几何参数** | $d$ | 外延层厚度（待求量） | nm 或 μm | 核心未知量 |
| | $\theta_0$ | 入射角（空气中） | rad | 可控实验参数 |
| | $\theta_1$ | 折射角（外延层中） | rad | 由Snell定律确定 |
| | $\theta_2$ | 折射角（衬底中） | rad | 由Snell定律确定 |
| **光学常数** | $n_0$ | 空气折射率 | 1 | 通常取1.0003或近似为1 |
| | $n_1(\lambda)$ | 外延层相折射率 | — | 波长依赖，需精确标定 |
| | $n_2(\lambda)$ | 衬底相折射率 | — | 已知材料参数 |
| | $n_{g,1}$ | 外延层群折射率 | — | $n_g = n - \lambda\frac{dn}{d\lambda}$ |
| | $\lambda$ | 真空波长 | nm | 光谱扫描变量 |
| **振幅系数** | $r_{01}^{(s)}, r_{01}^{(p)}$ | 空气-外延层界面反射系数 | — | Fresnel公式，上标区分偏振 |
| | $r_{12}^{(s)}, r_{12}^{(p)}$ | 外延层-衬底界面反射系数 | — | Fresnel公式 |
| | $t_{01}, t_{10}$ | 透射系数（正向/反向） | — | Stokes倒逆关系关联 |
| **能量参数** | $R_1 = \|r_{01}\|^2$ | 上界面反射率 | — | $0 \leq R_1 < 1$ |
| | $R_2 = \|r_{12}\|^2$ | 下界面反射率 | — | $0 \leq R_2 < 1$ |
| | $R_{eff} = R_1 R_2$ | 有效往返反射率 | — | 多光束干涉品质因子 |
| | $T_1 = 1-R_1$ | 上界面透射率 | — | 无吸收假设 |
| **相位参数** | $\delta$ | 相邻光束相位差 | rad | 由相折射率严格定义 |
| | $\phi_r$ | 总反射光相位 | rad | Airy函数相位响应 |
| | $\Delta\phi_{Gouy}$ | Goos-Hänchen相位修正 | rad | 全反射时非零 |
| **仪器参数** | $L_c$ | 光源相干长度 | μm | $L_c \approx \lambda^2/\Delta\lambda$ |
| | $\mathcal{F}$ | 干涉仪精细度 | — | 条纹锐度度量 |
| | $\mathcal{F}_{eff}$ | 有效精细度 | — | 含光源线宽、缺陷等退化 |
| **测量量** | $I_r(\lambda)$ | 反射光强谱 | a.u. | 实验获取数据 |
| | $I_t(\lambda)$ | 透射光强谱 | a.u. | 备选测量模式 |

---

### 二、核心数学模型建立

#### 2.1 基础电磁边界条件：Fresnel系数的严格形式

光波在分层介质界面处的振幅反射与透射由Maxwell方程组的电磁场边界连续性导出。对于各向同性介质界面，入射面内的p偏振（TM波，电场在入射面内）与垂直入射面的s偏振（TE波，电场垂直入射面）需分别处理，二者的Fresnel系数存在本质差异。

**s偏振（TE波）界面反射系数：**

$$\boxed{r_{ij}^{(s)} = \frac{n_i\cos\theta_i - n_j\cos\theta_j}{n_i\cos\theta_i + n_j\cos\theta_j}} \tag{1}$$

**p偏振（TM波）界面反射系数：**

$$\boxed{r_{ij}^{(p)} = \frac{n_j\cos\theta_i - n_i\cos\theta_j}{n_j\cos\theta_i + n_i\cos\theta_j}} \tag{2}$$

**Snell折射定律约束：**

$$\boxed{n_0\sin\theta_0 = n_1\sin\theta_1 = n_2\sin\theta_2} \tag{3}$$

公式(1)-(2)的物理意义在于：界面反射系数由波矢法向分量的阻抗失配决定，是后续所有干涉计算的基石。特别需要注意的是，p偏振的Fresnel公式(2)与s偏振(1)并非简单的余弦替换关系，而是分子分母中折射率与余弦因子的交叉换位，这一结构导致p偏振存在Brewster角（$r_{ij}^{(p)}=0$）而s偏振不存在。当$n_1 > n_0$且光从光疏到光密介质入射时，$r_{01}^{(s)} < 0$而$r_{01}^{(p)}$的符号取决于角度，导致两种偏振的干涉条纹可能存在$\pi$相位差，在厚度反演中必须精确处理。

**Stokes倒逆关系与能量守恒：**

基于时间反演对称性，Stokes建立了正向与反向透射系数的严格关系。设光从介质$i$入射到介质$j$，再考虑反向过程，结合能量守恒可得：

$$\boxed{t_{ij}t_{ji} = 1 - r_{ij}^2 \quad (\text{s偏振})} \tag{4a}$$

$$\boxed{t_{ij}t_{ji} = \frac{\cos\theta_j}{\cos\theta_i}\left(1 - r_{ij}^2\right) \quad (\text{一般形式})} \tag{4b}$$

公式(4b)为广义能量守恒形式，其中$\cos\theta_j/\cos\theta_i$因子源于p偏振情况下坡印廷矢量法向分量的投影修正。对于s偏振，由于电场始终垂直入射面，该投影因子为1，退化为(4a)。在正入射（$\theta_i = \theta_j = 0$）时，两种偏振统一，$t_{ij}t_{ji} = 1-R_{ij}$。

#### 2.2 多光束干涉的严格振幅递推与Airy公式

设入射光振幅为$E_0$，进入外延层后，光在上界面内侧的第一次反射振幅为$E_0 t_{01} r_{12} t_{10} e^{i\delta}$（往返相位累积$\delta$）。经过系统性的几何级数求和，总反射振幅为：

$$E_r = E_0\left[ r_{01} + t_{01}t_{10}r_{12}e^{i\delta}\sum_{m=0}^{\infty}\left(r_{10}r_{12}e^{i\delta}\right)^m \right]$$

利用$r_{10} = -r_{01}$（Stokes关系，从光密到光疏反射系数反号）及几何级数收敛条件$|r_{01}r_{12}| < 1$，求和得：

$$\boxed{E_r = E_0\frac{r_{01} + r_{12}e^{i\delta}}{1 + r_{01}r_{12}e^{i\delta}}} \tag{5}$$

此即多光束干涉反射振幅的严格表达式，与Born-Wolf《光学原理》第7章式(57)一致。对应的反射光强为：

$$\boxed{\frac{I_r}{I_0} = \frac{R_1 + R_2 + 2\sqrt{R_1R_2}\cos\delta}{1 + R_1R_2 + 2\sqrt{R_1R_2}\cos\delta}} \tag{6}$$

引入有效反射率$R_{eff} = R_1R_2$及精细度系数$F = \frac{4R_{eff}}{(1-R_{eff})^2}$，可将式(6)改写为标准的Airy公式：

$$\boxed{\frac{I_r}{I_0} = \frac{F\sin^2(\delta/2)}{1 + F\sin^2(\delta/2)} \cdot \frac{(1-R_1)(1-R_2)}{(1-R_{eff})^2} + R_{\text{min}}} \tag{7}$$

当$R_1 = R_2 = R$时，式(7)简化为Born-Wolf标准形式：

$$\boxed{\frac{I_r}{I_0} = \frac{F\sin^2(\delta/2)}{1 + F\sin^2(\delta/2)}} \tag{8}$$

其中精细度系数$F = \frac{4R}{(1-R)^2}$，与干涉仪精细度$\mathcal{F}$的关系为$\mathcal{F} = \frac{\pi\sqrt{F}}{2} = \frac{\pi\sqrt{R}}{1-R}$。

#### 2.3 干涉相位差的严格定义：相折射率的唯一性

相邻两束反射光之间的相位差$\delta$由光在外延层中的往返光程决定。根据电磁理论，单色稳态波的相位传播由相折射率$n_1$描述，群折射率$n_g$仅表征波包（脉冲）的能量传播速度，不参与稳态干涉相位计算。

$$\boxed{\delta = \frac{4\pi n_1(\lambda) d \cos\theta_1}{\lambda}} \tag{9}$$

式(9)中的$n_1(\lambda)$严格为相折射率，这是稳态干涉的核心物理要求。群折射率$n_{g,1} = n_1 - \lambda\frac{dn_1}{d\lambda}$仅在以下场景出现：(a) 脉冲时延测量；(b) 白光干涉的包络峰值定位；(c) 色散介质中的波包传播分析。对于光谱扫描型红外干涉法，厚度反演必须基于式(9)的相折射率，任何混淆将导致系统性误差。

当外延层存在色散时，干涉级次$m$与波长的关系为：

$$\boxed{m(\lambda) = \frac{2n_1(\lambda)d\cos\theta_1}{\lambda}} \tag{10}$$

相邻条纹的波长间隔（自由光谱范围）为：

$$\boxed{\Delta\lambda_{FSR} = \frac{\lambda^2}{2n_{g,1}d\cos\theta_1}} \tag{11}$$

注意式(11)中出现群折射率$n_{g,1}$，这是因为$\Delta\lambda_{FSR}$描述的是条纹包络的周期特性，涉及不同波长成分的群速度匹配，而非单一波长的相位条件。

#### 2.4 碳化硅外延层的各向异性修正

碳化硅（SiC）属于六角晶系（6mm点群），具有单轴晶体的光学各向异性。其介电张量在主轴坐标系中表示为$\varepsilon_{ij} = \text{diag}(\varepsilon_\perp, \varepsilon_\perp, \varepsilon_\parallel)$，对应寻常光折射率$n_o = \sqrt{\varepsilon_\perp}$和非寻常光折射率$n_e = \sqrt{\varepsilon_\parallel}$。

对于4H-SiC，室温下$n_o \approx 2.605$，$n_e \approx 2.673$（$\lambda = 500$ nm），双折射率$\Delta n = n_e - n_o \approx 0.068$。外延层生长方向通常为[0001]（c轴），此时：

- **光沿c轴传播（正入射）**：$n_1 = n_o = n_e$，表现为各向同性，无双折射效应；
- **光斜入射**：折射率取决于偏振方向与c轴的夹角，p偏振和s偏振经历不同的有效折射率。

在本题的红外干涉测量中，若采用正入射或近正入射配置（$\theta_0 \approx 0$），双折射效应可忽略，$n_1$取为$c$轴方向的等效折射率。若采用大角度斜入射（如$\theta_0 > 30^\circ$），则需区分o光和e光，分别建立干涉模型。基于题目所述"红外光入射"的常规配置及工业标准测试方法（通常采用近正入射以简化模型），本文后续分析忽略双折射效应，但明确标注此近似成立的条件为$\theta_0 \ll \arcsin(n_o/n_e)$。

---

### 三、多光束干涉的可观测条件分析

#### 3.1 从"必要条件"到"可观测条件"的重构

多光束干涉的物理发生无需额外条件——只要薄膜存在平行界面，光即产生无限序列的多次反射。然而，实验中能否观测到多光束干涉的特征（高精细度条纹、非正弦强度分布），取决于一系列"可观测条件"（observability conditions）。本文将可观测条件量化为三个层级的判据。

**层级一：相干条件（时间相干性）**

光源的有限线宽导致相位随机涨落，要求光程差小于相干长度：

$$\boxed{2n_1d\cos\theta_1 \leq L_c = \frac{\lambda^2}{\Delta\lambda_{FWHM}}} \tag{12}$$

对于傅里叶变换红外光谱仪（FTIR），典型光源线宽$\Delta\lambda \approx 1-10$ nm（中红外区$\lambda \approx 2-20$ μm），对应$L_c \approx 4-400$ μm。SiC外延层厚度通常为$1-50$ μm，通常满足式(12)。

**层级二：振幅可分辨条件（空间相干性）**

高阶透射光束的振幅需高于探测阈值。第$m$次反射光束的相对振幅为：

$$\frac{|E^{(m)}|}{|E^{(0)}|} = (R_1R_2)^{m/2} = R_{eff}^{m/2}$$

设探测阈值要求相邻光束振幅比至少为$\epsilon_{th}$（典型值0.1，对应强度比0.01），则有效反射率需满足：

$$\boxed{R_{eff} = R_1R_2 \geq \epsilon_{th}^2 \approx 0.01} \tag{13}$$

**层级三：条纹对比度条件（仪器响应）**

实际仪器存在有限分辨率、探测器噪声、界面粗糙度等退化因素，定义有效精细度：

$$\boxed{\frac{1}{\mathcal{F}_{eff}^2} = \frac{1}{\mathcal{F}_{R}^2} + \frac{1}{\mathcal{F}_{D}^2} + \frac{1}{\mathcal{F}_{\lambda}^2} + \frac{1}{\mathcal{F}_{defect}^2}} \tag{14}$$

其中$\mathcal{F}_{R} = \pi\sqrt{R_{eff}}/(1-R_{eff})$为反射率限制精细度，$\mathcal{F}_{D}$为探测器空间分辨率限制，$\mathcal{F}_{\lambda}$为光源线宽限制，$\mathcal{F}_{defect}$为界面缺陷（粗糙度、楔形）限制。当$\mathcal{F}_{eff} \gtrsim 3$时，多光束干涉的非正弦特征方可辨识。

#### 3.2 SiC/Si与Si/Si界面的$R_{eff}$估算与多光束显著性预判

**SiC外延层/SiC衬底界面（附件1、2）：**

SiC的折射率$n_{SiC} \approx 2.55-2.65$（红外区，随波长变化），外延层与衬底的折射率差异源于掺杂载流子浓度。典型掺杂浓度$n_{epi} \approx 10^{15}-10^{16}$ cm$^{-3}$，$n_{sub} \approx 10^{18}-10^{19}$ cm$^{-3}$。根据Drude模型，载流子引起的折射率变化：

$$\Delta n = -\frac{n_e e^2}{2\varepsilon_0 m^* \omega^2}$$

对于SiC，$m^* \approx 0.29m_0$，在$\lambda = 10$ μm处，$\Delta n/n \approx 10^{-3}-10^{-2}$。因此：

$$n_1 \approx 2.60, \quad n_2 \approx 2.60(1 \pm 0.01)$$

界面反射率：

$$R_{12} = \left(\frac{n_1 - n_2}{n_1 + n_2}\right)^2 \approx \left(\frac{0.026}{5.2}\right)^2 \approx 2.5 \times 10^{-5}$$

上界面空气-SiC反射率：

$$R_{01} = \left(\frac{1 - 2.6}{1 + 2.6}\right)^2 \approx 0.198$$

有效往返反射率：

$$\boxed{R_{eff}^{(SiC)} = R_{01}R_{12} \approx 4.9 \times 10^{-6} \ll 0.01} \tag{15}$$

**结论：** SiC外延层/衬底界面的折射率对比极弱，$R_{eff}$远低于可观测阈值，多光束干涉效应完全不可分辨。双光束近似（问题1的模型）已足够精确。

**Si外延层/Si衬底界面（附件3、4）：**

Si的折射率$n_{Si} \approx 3.42-3.48$（近红外，$\lambda \approx 1.1-2.5$ μm），掺杂引起的折射率变化同样由Drude模型描述，但Si中$m^* \approx 0.26m_0$，且近红外区光子能量较高，$\Delta n/n$可达$10^{-2}-10^{-1}$量级。典型值$n_{epi} \approx 3.45$，$n_{sub} \approx 3.50$：

$$R_{12} = \left(\frac{0.05}{6.95}\right)^2 \approx 5.2 \times 10^{-5}$$

$$R_{01} = \left(\frac{1 - 3.45}{1 + 3.45}\right)^2 \approx 0.303

在正式建立硅晶圆多光束干涉修正模型之前，必须首先严格依据Born与Wolf《光学原理》第7章的框架，从电磁边界条件出发重构多光束干涉的理论基础。传统教材中常见的简化处理往往隐含了$R_{01} = R_{12}$的不合理假设，这在硅外延层/衬底系统中由于掺杂浓度差异导致的折射率失配情形下将引入系统性误差。

设入射光从空气（介质0，折射率$n_0=1$）以入射角$\theta_0$入射至外延层（介质1，复折射率$\tilde{n}_1 = n_1 + i\kappa_1$），外延层厚度为$d$，衬底为同种材料但掺杂浓度不同的硅（介质2，复折射率$\tilde{n}_2 = n_2 + i\kappa_2$）。根据Snell定律的复数推广形式：

$$\tilde{n}_0\sin\theta_0 = \tilde{n}_1\sin\tilde{\theta}_1 = \tilde{n}_2\sin\tilde{\theta}_2 \tag{6}$$

其中$\tilde{\theta}_1$为复折射角，满足$\cos\tilde{\theta}_1 = \sqrt{1-\sin^2\tilde{\theta}_1}$，根号分支取实部为正以保证物理上的衰减波行为。

对于$s$偏振（TE波，电场垂直于入射面），界面$(j,k)$的振幅反射与透射系数由Fresnel公式严格给出：

$$r_{jk}^{(s)} = \frac{\tilde{n}_j\cos\tilde{\theta}_j - \tilde{n}_k\cos\tilde{\theta}_k}{\tilde{n}_j\cos\tilde{\theta}_j + \tilde{n}_k\cos\tilde{\theta}_k}, \quad t_{jk}^{(s)} = \frac{2\tilde{n}_j\cos\tilde{\theta}_j}{\tilde{n}_j\cos\tilde{\theta}_j + \tilde{n}_k\cos\tilde{\theta}_k} \tag{7}$$

对于$p$偏振（TM波，磁场垂直于入射面），形式为：

$$r_{jk}^{(p)} = \frac{\tilde{n}_k\cos\tilde{\theta}_j - \tilde{n}_j\cos\tilde{\theta}_k}{\tilde{n}_k\cos\tilde{\theta}_j + \tilde{n}_j\cos\tilde{\theta}_k}, \quad t_{jk}^{(p)} = \frac{2\tilde{n}_j\cos\tilde{\theta}_j}{\tilde{n}_k\cos\tilde{\theta}_j + \tilde{n}_j\cos\tilde{\theta}_k} \tag{8}$$

关键注意：在吸收介质情形下，$\tilde{n}_j\cos\tilde{\theta}_j$为复数，上述系数均为复数，需严格遵循复数运算规则。Stokes关系在复数域的推广为：

$$t_{jk}t_{kj} = 1 - r_{jk}^2, \quad r_{kj} = -r_{jk} \tag{9}$$

此处$r_{jk}^2 \neq |r_{jk}|^2$，必须为复数平方。

考虑光波在外延层内的多次反射与透射，第$m$束出射光相对于第一束的累积相位延迟为：

$$\tilde{\delta} = \frac{4\pi}{\lambda}\tilde{n}_1 d\cos\tilde{\theta}_1 = \delta_r + i\delta_i \tag{10}$$

其中实部$\delta_r = 4\pi n_1 d\cos\theta_{1r}/\lambda$决定干涉振荡，虚部$\delta_i = 4\pi\kappa_1 d/\lambda\cos\theta_{1r}$（正入射近似下）描述振幅衰减。各次反射光的复振幅构成等比级数，公比为$r_{12}r_{10}e^{i\tilde{\delta}} = -r_{12}r_{01}e^{i\tilde{\delta}}$。

对无限级数求和，总反射复振幅严格表达式为：

$$\boxed{r_{tot}^{(s/p)} = \frac{r_{01}^{(s/p)} + r_{12}^{(s/p)}e^{i\tilde{\delta}}}{1 + r_{01}^{(s/p)}r_{12}^{(s/p)}e^{i\tilde{\delta}}}} \tag{11}$$

此即Born-Wolf第7章式(27)的一般形式，适用于任意偏振态、任意吸收程度及任意折射率对比度。反射强度为：

$$\boxed{R_{multi}^{(s/p)} = r_{tot}^{(s/p)} \cdot \left(r_{tot}^{(s/p)}\right)^* = \frac{|r_{01}|^2 + |r_{12}|^2e^{-2\delta_i} + 2\text{Re}\left(r_{01}r_{12}^*e^{-i\tilde{\delta}^*}\right)}{1 + |r_{01}r_{12}|^2e^{-2\delta_i} + 2\text{Re}\left(r_{01}r_{12}e^{i\tilde{\delta}}\right)}} \tag{12}$$

对于非偏振光或随机偏振测量，取统计平均：

$$\boxed{R_{multi} = \frac{R_{multi}^{(s)} + R_{multi}^{(p)}}{2}} \tag{13}$$

**关于Airy函数的适用性修正**：标准教科书常将式(12)简化为对称形式的Airy函数，其隐含前提是$|r_{01}| = |r_{12}|$且界面无吸收。在硅外延层/衬底系统中，由于掺杂导致的折射率差异，$R_{01} = |r_{01}|^2 \neq R_{12} = |r_{12}|^2$，传统Airy函数式(5)失效。正确的处理方式是直接采用式(11)-(12)的复数形式进行数值计算，或推导非对称修正的Airy表达式。

定义非对称参数$\rho = \sqrt{R_{01}/R_{12}}$，当$\rho \neq 1$时，反射率的极值位置发生偏移，且极值比不再由精细度唯一决定。非对称Airy函数的显式形式为：

$$\boxed{R_{asym} = \frac{R_{01} + R_{12}e^{-2\delta_i} - 2\sqrt{R_{01}R_{12}}e^{-\delta_i}\cos(\delta_r + \phi_{12} - \phi_{01})}{1 + R_{01}R_{12}e^{-2\delta_i} + 2\sqrt{R_{01}R_{12}}e^{-\delta_i}\cos(\delta_r + \phi_{01} + \phi_{12})}} \tag{14}$$

其中$r_{01} = \sqrt{R_{01}}e^{i\phi_{01}}$，$r_{12} = \sqrt{R_{12}}e^{i\phi_{12}}$。当$R_{01} = R_{12} = R$且$\phi_{01} = \phi_{12} = 0$（无吸收、对称界面）时，式(14)退化为标准Airy函数。在数值实现中，建议统一采用式(11)的复数形式以避免简化错误。

为建立多光束干涉必要性判据的显式表达式，需从相干条件与可观测性两个维度分析。设光谱仪波长分辨率为$\Delta\lambda$，干涉级次为$m = 2n_1 d/\lambda$（正入射），相邻条纹角频率间隔为$\Delta\omega = \pi c/(n_1 d)$。多光束干涉使条纹锐化，有效半高全宽为：

$$\boxed{\Delta\omega_{1/2} = \frac{\Delta\omega}{\mathcal{F}_{eff}} = \frac{\pi c}{n_1 d \mathcal{F}_{eff}}} \tag{15}$$

其中有效精细度：

$$\boxed{\mathcal{F}_{eff} = \frac{\pi\sqrt[4]{R_{01}R_{12}}e^{-\delta_i/2}}{1 - \sqrt{R_{01}R_{12}}e^{-\delta_i}}} \tag{16}$$

仪器可分辨多光束结构的必要条件为光谱分辨率优于条纹宽度：

$$\boxed{\frac{\Delta\lambda}{\lambda} < \frac{1}{2m\mathcal{F}_{eff}} = \frac{\lambda}{4n_1 d \mathcal{F}_{eff}}} \tag{17}$$

此外，条纹对比度需高于探测阈值。定义多光束与双光束模型的反射率差异对比度：

$$\boxed{\mathcal{C} = \frac{|R_{multi} - R_{double}|_{max}}{R_{double}^{max} - R_{double}^{min}}} \tag{18}$$

当$\mathcal{C} > 0.1$时，多光束效应不可忽略。综合式(17)-(18)构成完整的必要性判据体系。

硅材料掺杂引起的折射率变化需定量估计。根据Soref与Bennett的经典工作（J. Appl. Phys. 1987），硅在通信波段（$\lambda \approx 1.3-1.55\ \mu$m）的折射率变化与载流子浓度关系为：

$$\boxed{\Delta n = -\frac{e^2\lambda^2}{8\pi^2 c^2 \varepsilon_0 n_{Si}}\left(\frac{N_e}{m_e^*} + \frac{N_h^{0.8}}{m_h^*}\right)} \tag{19}$$

$$\boxed{\Delta\kappa = \frac{e^3\lambda^3}{16\pi^3 c^3 \varepsilon_0 n_{Si}}\left(\frac{N_e}{m_e^{*2}\mu_e} + \frac{N_h}{m_h^{*2}\mu_h}\right)} \tag{20}$$

其中$N_e$、$N_h$为电子与空穴浓度，$m_e^* = 0.26m_0$、$m_h^* = 0.39m_0$为有效质量，$\mu_e$、$\mu_h$为迁移率。对于典型外延层掺杂$N_{epi} \sim 10^{15}\ \text{cm}^{-3}$与衬底掺杂$N_{sub} \sim 10^{19}\ \text{cm}^{-3}$，在$\lambda = 900\ \text{nm}$处：

$$\Delta n = n_{epi} - n_{sub} \approx -(2-5) \times 10^{-3}, \quad \Delta\kappa \approx (1-3) \times 10^{-4} \tag{21}$$

此折射率差异虽小，但足以使$R_{01} \neq R_{12}$，破坏Airy函数的对称前提。更关键的是，在可见光至近红外区（$\lambda < 1000\ \text{nm}$），硅的本征吸收系数$\alpha = 4\pi\kappa/\lambda$显著，导致：

$$\delta_i = \frac{\alpha d}{2} \sim 0.1-1.0 \quad (\text{对}\ d \sim 1-10\ \mu\text{m}) \tag{22}$$

这强烈抑制高阶多次反射，等效降低精细度，使多光束效应部分被吸收衰减所掩盖。

对比Si与SiC的关键光学参数：SiC在红外区（$\lambda > 4\ \mu\text{m}$）具有$\alpha < 10\ \text{cm}^{-1}$的极低吸收，折射率$n_{SiC} \approx 2.6$且对掺杂不敏感（宽禁带导致本征载流子浓度极低）；而Si在$\lambda = 1\ \mu\text{m}$处$\alpha \sim 10^3\ \text{cm}^{-1}$，且$\Delta n/\Delta N$比SiC大两个数量级。这解释了为何SiC红外干涉法成为行业标准——低吸收保证高精细度多光束干涉，弱掺杂依赖简化模型；而Si的可见光测量因强吸收导致信号衰减、条纹对比度低，且掺杂引起的折射率梯度使界面模糊，厚度反演困难。

针对附件3-4硅晶圆数据的多光束干涉识别，实施以下判别流程：

**步骤一：参数预设与数据预处理**
- 外延层与衬底均为硅，但掺杂浓度不同。根据晶圆规格，设$N_{epi} = 1\times 10^{15}\ \text{cm}^{-3}$，$N_{sub} = 5\times 10^{18}\ \text{cm}^{-3}$
- 采用Soref-Bennett公式计算$\tilde{n}_1(\lambda)$、$\tilde{n}_2(\lambda)$，波长范围200-1000 nm
- 对实测光谱$R_{exp}(\lambda)$进行Savitzky-Golay平滑，去除仪器噪声

**步骤二：双光束与多光束模型拟合对比**
建立优化目标函数：

$$\boxed{\chi^2(d) = \sum_i \frac{\left[R_{exp}(\lambda_i) - R_{model}(\lambda_i; d)\right]^2}{\sigma_i^2}} \tag{23}$$

分别用双光束模型$R_{double}$（式(11)仅保留分子）与多光束模型$R_{multi}$（完整式(11)-(12)）拟合。若$\chi^2_{multi}/\chi^2_{double} < 0.9$且残差呈现系统性而非随机分布，则判定多光束效应显著。

**步骤三：必要性判据数值验证**
对候选厚度$d^{(0)}$，计算：
- 干涉级次$m = 2\bar{n}d^{(0)}/\lambda_{center}$
- 有效精细度$\mathcal{F}_{eff}$由式(16)
- 光谱分辨率条件式(17)
- 对比度阈值式(18)

若式(17)与式(18)同时满足，则在数学上确认多光束干涉的必要性；若仅满足其一，需结合物理分析判断。

**步骤四：厚度反演算法**

采用Levenberg-Marquardt非线性最小二乘，核心迭代：

$$\boxed{\mathbf{J}^T\mathbf{W}\mathbf{J}\Delta\mathbf{p} = \mathbf{J}^T\mathbf{W}\left[\mathbf{R}_{exp} - \mathbf{R}_{multi}(\mathbf{p})\right]} \tag{24}$$

其中参数向量$\mathbf{p} = (d, n_{1,eff}, \kappa_{1,eff})^T$，雅可比矩阵$\mathbf{J}_{ij} = \partial R_{multi}(\lambda_i)/\partial p_j$，权重矩阵$\mathbf{W} = \text{diag}(1/\sigma_i^2)$。为增强鲁棒性，引入厚度先验约束：

$$\boxed{\chi^2_{total} = \chi^2_{fit} + \lambda_{reg}\left(\frac{d - d_{nom}}{\sigma_d}\right)^2} \tag{25}$$

正则化参数$\lambda_{reg}$通过L曲线法确定。

对附件3-4硅晶圆的具体计算，假设测得光谱在$\lambda \in [400, 900]$ nm范围内呈现振荡条纹。经Soref-Bennett公式计算，该波段内$\Delta n \approx 0.003-0.008$，对应：

$$R_{01} = \left|\frac{1-\tilde{n}_1}{1+\tilde{n}_1}\right|^2 \approx 0.30, \quad R_{12} = \left|\frac{\tilde{n}_1-\tilde{n}_2}{\tilde{n}_1+\tilde{n}_2}\right|^2 \approx (1-5)\times 10^{-5} \tag{26}$$

关键发现：由于外延层与衬底均为硅，掺杂导致的折射率差异极小，$R_{12} \ll R_{01}$，下界面近乎全透而非高反。此时$r_{01}r_{12} \approx 0$，式(11)分母$\approx 1$，多光束干涉效应被强烈抑制！这与SiC外延层/衬底系统形成鲜明对比——在SiC中，外延层与衬底虽为同种材料，但红外区极低吸收与弱掺杂依赖使$R_{12}$不可忽略，多光束效应显著。

然而，上述分析基于体材料近似。实际硅外延层界面存在载流子浓度梯度（过渡区宽度$w \sim 10-100$ nm），形成有效折射率渐变层。当过渡区宽度与波长可比拟时，需采用等效膜层模型修正。设过渡区折射率剖面为：

$$\tilde{n}(z) = \tilde{n}_{epi} + \frac{\tilde{n}_{sub}-\tilde{n}_{epi}}{2}\left[1 + \tanh\left(\frac{z-z_0}{w}\right)\right] \tag{27}$$

采用矩阵方法或分段均匀近似计算有效反射系数。过渡区的存在等效增大$R_{12}$，可能恢复部分多光束特性。

综合以上分析，对附件3-4硅晶圆的判定结论为：在理想突变界面假设下，由于硅材料掺杂导致的折射率差异过小（$\Delta n/n \sim 10^{-3}$），多光束干涉效应极弱，双光束模型已足够精确；若实测光谱呈现异常锐化的条纹或强度调制，则需考虑界面过渡区的等效多光束效应，此时应采用渐变折射率模型或等效三层膜模型修正。最终厚度计算需以式(11)-(12)的完整数值实现为基准，避免对称Airy函数的误用，并通过式(17)-(18)的判据体系进行模型自洽性验证。

基于多光束干涉的物理机制，建立完整的数学模型来评估并消除碳化硅数据中的多光束干涉影响。

---

## 一、变量与参数定义

| 符号 | 类型 | 物理意义 | 单位 |
|:---|:---|:---|:---|
| $d$ | 待求变量 | 碳化硅外延层真实厚度 | $\mu$m 或 nm |
| $d_{\text{eff}}$ | 导出变量 | 双光束模型拟合的等效厚度 | $\mu$m 或 nm |
| $\lambda$ | 输入参数 | 入射光波长 | nm |
| $\tilde{\nu} = 1/\lambda$ | 输入参数 | 波数 | cm$^{-1}$ |
| $n_1$ | 已知参数 | 碳化硅外延层折射率（实部） | 无量纲 |
| $n_0$ | 已知参数 | 入射介质折射率（空气 $n_0 \approx 1$） | 无量纲 |
| $n_2$ | 已知参数 | 衬底折射率 | 无量纲 |
| $\tilde{n}_1 = n_1 + i\kappa_1$ | 已知参数 | 外延层复折射率 | 无量纲 |
| $\tilde{n}_2 = n_2 + i\kappa_2$ | 已知参数 | 衬底复折射率 | 无量纲 |
| $\theta_0$ | 输入参数 | 入射角 | rad 或 ° |
| $\theta_1$ | 导出参数 | 折射角（复Snell定律确定） | rad |
| $\tilde{r}_{01}, \tilde{r}_{12}$ | 导出参数 | 复振幅反射系数 | 无量纲 |
| $\rho_{01} = |\tilde{r}_{01}|$, $\rho_{12} = |\tilde{r}_{12}|$ | 导出参数 | 振幅反射率模 | 无量纲 |
| $\phi_{01}$, $\phi_{12}$ | 导出参数 | 反射相位跃变 | rad |
| $R = \rho_{01}\rho_{12}$ | 导出参数 | 等效反射率乘积 | 无量纲 |
| $F = 4R/(1-R)^2$ | 导出参数 | 精细度系数 | 无量纲 |
| $\mathcal{F} = \pi\sqrt{R}/(1-R)$ | 导出参数 | 精细度（finesse） | 无量纲 |
| $\delta = 4\pi n_1 d \cos\theta_1/\lambda$ | 核心变量 | 相邻光束相位差 | rad |
| $m$ | 整数变量 | 干涉级次 | 整数 |
| $k$ | 整数参数 | 条纹间隔数（用于波数差计算） | 整数 |
| $I_{\text{obs}}(\tilde{\nu})$ | 观测数据 | 实测反射/透射光谱强度 | a.u. |
| $L_c = \lambda^2/\Delta\lambda$ | 仪器参数 | 光源相干长度 | nm |
| $\Delta\lambda_{\text{inst}}$ | 仪器参数 | 光谱仪线宽（FWHM） | nm |
| $g(\tilde{\nu}-\tilde{\nu}')$ | 仪器函数 | 光谱仪仪器响应函数 | cm |
| $\sigma_{\text{noise}}$ | 统计参数 | 光谱噪声标准差 | a.u. |
| $\Delta\tilde{\nu}_{\text{abs}}$ | 导出变量 | 吸收导致的峰位移动 | cm$^{-1}$ |

---

## 二、核心数学模型

### 2.1 吸收介质中复振幅反射系数的严格推导

当外延层或衬底存在吸收时，折射率扩展为复数形式 $\tilde{n} = n + i\kappa$，其中消光系数 $\kappa$ 与吸收系数 $\alpha$ 的关系为 $\alpha = 4\pi\kappa/\lambda$。此时Snell定律推广为复数形式：

$$\tilde{n}_0\sin\theta_0 = \tilde{n}_1\sin\tilde{\theta}_1 = \tilde{n}_2\sin\tilde{\theta}_2 \tag{1}$$

其中 $\tilde{\theta}_1$ 为复折射角，满足 $\cos\tilde{\theta}_1 = \sqrt{1-\sin^2\tilde{\theta}_1}$，取实部为正的分支以保证物理上的衰减解。

**s偏振（TE波）的复振幅反射系数：**

$$\tilde{r}_{01}^{(s)} = \frac{\tilde{n}_0\cos\theta_0 - \tilde{n}_1\cos\tilde{\theta}_1}{\tilde{n}_0\cos\theta_0 + \tilde{n}_1\cos\tilde{\theta}_1} = \rho_{01}^{(s)}e^{i\phi_{01}^{(s)}} \tag{2}$$

$$\tilde{r}_{12}^{(s)} = \frac{\tilde{n}_1\cos\tilde{\theta}_1 - \tilde{n}_2\cos\tilde{\theta}_2}{\tilde{n}_1\cos\tilde{\theta}_1 + \tilde{n}_2\cos\tilde{\theta}_2} = \rho_{12}^{(s)}e^{i\phi_{12}^{(s)}} \tag{3}$$

**p偏振（TM波）的复振幅反射系数：**

$$\tilde{r}_{01}^{(p)} = \frac{\tilde{n}_1\cos\theta_0 - \tilde{n}_0\cos\tilde{\theta}_1}{\tilde{n}_1\cos\theta_0 + \tilde{n}_0\cos\tilde{\theta}_1} = \rho_{01}^{(p)}e^{i\phi_{01}^{(p)}} \tag{4}$$

$$\tilde{r}_{12}^{(p)} = \frac{\tilde{n}_2\cos\tilde{\theta}_1 - \tilde{n}_1\cos\tilde{\theta}_2}{\tilde{n}_2\cos\tilde{\theta}_1 + \tilde{n}_1\cos\tilde{\theta}_2} = \rho_{12}^{(p)}e^{i\phi_{12}^{(p)}} \tag{5}$$

**物理意义**：公式(2)-(5)是Fresnel公式在吸收介质中的严格推广。与透明介质情形不同，复折射角导致反射系数本身具有相位跃变 $\phi_{ij}$，且该相位与波长相关，构成色散耦合。对于SiC外延层，典型参数为 $n_1 \approx 2.55$，$\kappa_1 \sim 10^{-3}-10^{-2}$（依赖于掺杂浓度），衬底 $\kappa_2$ 通常更大，这使得 $\phi_{12}$ 不可忽略。

### 2.2 多光束干涉的严格Airy公式推导

考虑外延层内无限多次反射的相干叠加。设入射光振幅为 $E_0$，经过界面01反射的第一束光振幅为 $\tilde{r}_{01}E_0$，透射进入外延层后经界面12反射、再经界面10透射的第二束光振幅为 $\tilde{t}_{01}\tilde{r}_{12}\tilde{t}_{10}e^{i\delta/2}E_0$，其中 $\tilde{t}_{ij}$ 为透射系数，$\delta$ 为往返相位延迟。

第 $j$ 束出射光的复振幅为：
$$\tilde{E}_j = \tilde{t}_{01}\tilde{t}_{10}\tilde{r}_{12}(\tilde{r}_{10}\tilde{r}_{12})^{j-2}e^{i(j-1)\delta/2}E_0, \quad j \geq 2 \tag{6}$$

利用斯托克斯关系 $\tilde{r}_{10} = -\tilde{r}_{01}$（对复系数严格成立）及能量守恒的广义形式 $\tilde{t}_{01}\tilde{t}_{10} = 1-\tilde{r}_{01}^2$（非吸收极限），总反射振幅为几何级数求和：

$$\tilde{E}_r = \left[\tilde{r}_{01} + \frac{\tilde{t}_{01}\tilde{t}_{10}\tilde{r}_{12}e^{i\delta}}{1-\tilde{r}_{10}\tilde{r}_{12}e^{i\delta}}\right]E_0 = \frac{\tilde{r}_{01} + \tilde{r}_{12}e^{i\delta}}{1 + \tilde{r}_{01}\tilde{r}_{12}e^{i\delta}}E_0 \tag{7}$$

其中利用了 $\tilde{r}_{10} = -\tilde{r}_{01}$ 和 $\tilde{t}_{01}\tilde{t}_{10} = 1+\tilde{r}_{01}\tilde{r}_{10} = 1-\tilde{r}_{01}^2$。

**反射率的严格Airy公式：**

定义 $\tilde{r}_{01} = \rho_{01}e^{i\phi_{01}}$，$\tilde{r}_{12} = \rho_{12}e^{i\phi_{12}}$，则：

$$R_{\text{multi}} = \left|\frac{\tilde{E}_r}{E_0}\right|^2 = \frac{\rho_{01}^2 + \rho_{12}^2 + 2\rho_{01}\rho_{12}\cos(\delta + \phi_{12} - \phi_{01})}{1 + \rho_{01}^2\rho_{12}^2 + 2\rho_{01}\rho_{12}\cos(\delta + \phi_{12} + \phi_{01})} \tag{8}$$

**透射率的严格Airy公式：**

$$T_{\text{multi}} = \frac{n_2\cos\theta_2}{n_0\cos\theta_0}\cdot\frac{(1-\rho_{01}^2)(1-\rho_{12}^2)}{1 + \rho_{01}^2\rho_{12}^2 + 2\rho_{01}\rho_{12}\cos(\delta + \phi_{12} + \phi_{01})} \tag{9}$$

**关键区分**：公式(8)与(9)的分母相位项均为 $(\delta + \phi_{12} + \phi_{01})$，但分子相位项不同——反射光谱为 $(\delta + \phi_{12} - \phi_{01})$，透射光谱为常数。这一差异导致反射条纹与透射条纹的极值条件具有本质区别，不可混用。

### 2.3 反射光谱与透射光谱的条纹极值条件

**反射光谱的极值条件：**

对公式(8)求极值，令 $\partial R_{\text{multi}}/\partial\delta = 0$，得：

$$\sin(\delta + \phi_{12} - \phi_{01})\left[1 - \rho_{01}^2\rho_{12}^2\right] = 0 \tag{10}$$

由于 $1-\rho_{01}^2\rho_{12}^2 \neq 0$（非全反射情形），极值条件为：

$$\delta + \phi_{12} - \phi_{01} = m\pi, \quad m \in \mathbb{Z} \tag{11}$$

当 $m$ 为偶数时对应反射极小（相消干涉），$m$ 为奇数时对应反射极大（相长干涉）。注意：此结论仅在 $\rho_{01} > \rho_{12}$ 时成立；若 $\rho_{01} < \rho_{12}$（如存在增透膜结构），极值性质反转。

**透射光谱的极值条件：**

$$\delta + \phi_{12} + \phi_{01} = m\pi, \quad m \in \mathbb{Z} \tag{12}$$

$m$ 为偶数时透射极大，$m$ 为奇数时透射极小。

**波数差公式的严格推导：**

由相位差定义 $\delta = 4\pi n_1 d \tilde{\nu}\cos\theta_1$（注意：对吸收介质，$n_1$ 为复折射率实部，$\cos\theta_1$ 需由复Snell定律确定其实部），对相邻级次 $m$ 和 $m+k$：

$$\delta_{m+k} - \delta_m = 4\pi n_1 d \cos\theta_1 (\tilde{\nu}_{m+k} - \tilde{\nu}_m) = k\pi \tag{13}$$

解得：

$$\Delta\tilde{\nu}_k = \tilde{\nu}_{m+k} - \tilde{\nu}_m = \frac{k}{2n_1 d \cos\theta_1} \tag{14}$$

**量纲验证**：$[d] = \text{cm}$，$[n_1] = 1$，$[\cos\theta_1] = 1$，故 $[2n_1 d\cos\theta_1] = \text{cm}$，$[k/(2n_1 d\cos\theta_1)] = \text{cm}^{-1}$，与波数量纲一致。公式(14)是厚度反演的基础，但需注意其隐含假设：$n_1$ 和 $\theta_1$ 在 $\Delta\tilde{\nu}_k$ 范围内为常数，即色散可忽略。

### 2.4 多光束干涉的必要条件分析

多光束干涉显著区别于双光束干涉，需要满足严格的物理条件：

**条件一：高相干光源**

光源相干长度需满足：
$$L_c = \frac{\lambda^2}{\Delta\lambda} \gg 2n_1 d \cos\theta_1 \tag{15}$$

对于典型SiC外延层厚度 $d \sim 5-20\,\mu\text{m}$，$n_1 \approx 2.55$，往返光程 $2n_1 d \sim 25-100\,\mu\text{m}$。FTIR光谱仪的典型相干长度 $L_c \sim 1/\Delta\tilde{\nu}_{\text{res}} \sim 1\,\text{cm}$（对应分辨率 $1\,\text{cm}^{-1}$），远大于往返光程，条件满足。

**条件二：界面高反射率**

精细度系数 $F = 4R/(1-R)^2$ 需显著大于零，即 $R = \rho_{01}\rho_{12}$ 不可过小。对于SiC-空气界面，$\rho_{01} \approx (2.55-1)/(2.55+1) \approx 0.44$；SiC外延层-衬底界面因掺杂浓度梯度，$\rho_{12} \sim 0.01-0.1$，故 $R \sim 0.004-0.04$，$F \sim 0.016-0.17$。此值虽小，但足以导致可观测的多光束效应。

**条件三：光谱分辨率充足**

光谱仪分辨率需分辨多光束条纹的精细结构，即：
$$\delta\tilde{\nu}_{\text{inst}} < \frac{\Delta\tilde{\nu}_k}{\mathcal{F}} = \frac{1-R}{2\pi\sqrt{R}}\cdot\frac{1}{2n_1 d\cos\theta_1} \tag{16}$$

对于 $R=0.04$，$\mathcal{F} \approx 16.5$，条纹间隔 $\Delta\tilde{\nu}_1 \sim 40\,\text{cm}^{-1}$（$d=10\,\mu\text{m}$），则要求 $\delta\tilde{\nu}_{\text{inst}} < 2.4\,\text{cm}^{-1}$，常规FTIR可满足。

**条件四：外延层光学均匀性**

外延层内消光系数需满足 $\alpha d \ll 1$，即：
$$\kappa_1 \ll \frac{\lambda}{4\pi d} \sim 10^{-2} \tag{17}$$

高掺杂SiC外延层可能接近此边界，导致高阶光束衰减，等效降低 $R$。

### 2.5 多光束干涉对厚度计算的影响机制

**机制一：条纹对比度与精细度变化**

多光束干涉使条纹形状由正弦型转变为Airy函数型：

$$R_{\text{multi}} = \frac{F\sin^2(\delta_{\text{eff}}/2)}{1+F\sin^2(\delta_{\text{eff}}/2)} \cdot \frac{(1-R)^2}{(1-\rho_{01}^2)(1-\rho_{12}^2)} + R_{\text{min}} \tag{18}$$

其中 $\delta_{\text{eff}} = \delta + \phi_{12} - \phi_{01}$。条纹半高宽由双光束的 $\pi$ 压缩为 $\Delta\delta_{\text{FWHM}} = 4\arcsin[(1-R)/(2\sqrt{R})]$，精细度 $\mathcal{F} = \Delta\delta/(2\Delta\delta_{\text{FWHM}})$ 显著增大。

**机制二：吸收导致的真实峰位移动（核心物理效应）**

复折射率引入的相位色散使条纹峰位发生系统性移动。将 $\tilde{n}_1 = n_1(\tilde{\nu}) + i\kappa_1(\tilde{\nu})$ 代入，展开相位条件：

$$\delta = 4\pi d \cdot \text{Re}\left[\tilde{n}_1\cos\tilde{\theta}_1\right]\tilde{\nu} = 4\pi d\left[n_1\cos\theta_1' - \frac{n_1\kappa_1^2\sin^2\theta_0}{2(n_1^2+\kappa_1^2)^2\cos^3\theta_1'}\right]\tilde{\nu} \tag{19}$$

其中 $\theta_1'$ 为实Snell定律确定的角。第二项为吸收修正，导致有效光学厚度减小，峰位向高波数方向移动：

$$\Delta\tilde{\nu}_{\text{abs}} \approx \frac{2d\kappa_1^2\sin^2\theta_0}{(n_1^2+\kappa_1^2)^2\cos^3\theta_1'}\cdot\tilde{\nu}^2 \tag{20}$$

此效应与多光束的相位耦合 $\phi_{01}+\phi_{