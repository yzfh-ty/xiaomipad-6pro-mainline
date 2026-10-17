# OS3 分支：手动构建完整双系统候选包

本分支将 Android 侧基线改为 **OS3.0.7.0.VMYCNXM / Android 15**。
Ubuntu 仍使用 `kernel/source.json` 固定的主线内核，以及仓库已有的 Ubuntu 板级固件。
没有修改内核源码。Android 新 ROM 中的 DSP 与 Ubuntu 的固定 DSP 固件是两组独立输入。

目前只准备了适配代码和 ROM 身份；未在本地运行测试、编译或执行刷写。
首次完整构建和回归检查交给 Actions。成功产物仍是 `OFFLINE_ASSEMBLED`，不代表通过真机验证。

## 手动运行

1. 打开自己的主项目 Fork，在 **Actions** 中启用工作流。
2. 选择 **System image → Run workflow**，分支选 **main**。
3. 原厂线刷包下载地址已固定在 `tools/lib/liuqin-rom-images.json`，无需填写链接。
4. `ubuntu_url` 可留空；如提供镜像，必须与项目固定的 Ubuntu 26.04 ARM64 ISO 逐字节相同。
5. `kernel_repository` 留空会使用 `你的用户名/linux-sm8450-liuqin`。
   本次对应 `yzfh-ty/linux-sm8450-liuqin`，仍按固定提交构建，而非自动追随分支最新提交。
6. 点击 **Run workflow**。完成后在该次运行的 **Artifacts** 下载候选安装包和 Android boot 附件。

也可通过已登录的 GitHub CLI 手动运行：

```sh
gh workflow run image.yml --repo yzfh-ty/xiaomipad-6pro-mainline \
  --ref main
```

工作流位于 Fork 的默认分支 `main`。
本流程不自动创建公开 Release，也不自动刷写平板。

## 固定原厂包

```text
liuqin_images_OS3.0.7.0.VMYCNXM_20260514.0000.00_15.0_cn_f57d372b08.tgz
bytes: 7541014730
sha256: 9b33c813b7245ef67b1f55555bb3e769de2f13636e9c04f12bfb3788c5337359
```

固定下载地址：

[OS3.0.7.0.VMYCNXM 原厂线刷包](https://bkt-sgp-miui-ota-update-alisgp.oss-ap-southeast-1.aliyuncs.com/OS3.0.7.0.VMYCNXM/liuqin_images_OS3.0.7.0.VMYCNXM_20260514.0000.00_15.0_cn_f57d372b08.tgz)

工作流校验归档、9 个镜像、anti_version.txt，
并逐文件核对 14 个原厂 DTB 和 44 个 DTBO，校验失败即停止。
原厂归档、super 和私有设备数据不会放进候选安装包。

## 构建机和流程

默认使用 `ubuntu-24.04` GitHub runner，按顺序执行：
依赖与 CI 检查 → OS3 输入 → 固定 Ubuntu 桌面 → 设备组件 → 固定内核 → 整包装配 → 校验 → 上传。
传感器和 Settings 在隔离的 ARM64 根目录中通过 QEMU 构建，单个任务上限 360 分钟。

构建前会清理一次性 GitHub runner 预装的大型 SDK，并要求至少 45 GiB 可用空间。
GitHub 标准 runner 的保证资源不等于本项目的磁盘需求，不能保证每次都能满足整包构建。
空间不足时会在大文件下载前停止；可把仓库变量 `LIUQIN_IMAGE_RUNNER` 改为容量更大的
Linux x86-64 runner 标签。自托管 runner 不执行预装 SDK 清理，但仍要求全新工作目录与免交互 sudo。
参考 [GitHub runner 资源说明](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。

7-Zip 使用 [官方 26.03 Linux x64 发布文件](https://github.com/ip7z/7zip/releases/tag/26.03)
及其固定 SHA256。AOSP mkbootimg 使用固定 Git 提交和既有脚本内容校验，避免依赖可变的归档封装。
Ubuntu 板级固件从仓库内的固定清单重建输入布局，不从 OS3 随意替换 Ubuntu 固件。

Python 依赖由 APT 安装，其中 [python3-lz4](https://packages.ubuntu.com/noble/python3-lz4)
提供 Android ramdisk 补丁需要的 `lz4.block`，与 `lz4` 命令行软件包分开。
工作流优先使用 `/usr/bin/python3`，并在下载 ROM 前检查模块和压缩往返自检。

桌面清单的旧格式包含宿主机解析的用户和组名称。原构建机的清单 SHA256 为
`175ca2299263545973831606e397cce3fbc79298d97eb0bd7e216ac34944eed7`；
本次 GitHub runner 在 ISO/casper 校验通过后生成的清单 SHA256 为
`43c5325645f920b659ebe942357a0b727798ede808328ed39e4b2839175f5a89`。
根文件系统构建器仅接受这两份明确固定的清单身份，并记录实际使用值；其他值仍拒绝。
提取 Ubuntu 后即运行 `verify-desktop`，在传感器和 Settings 编译前完成这项检查。

SSC 模拟测试依赖构建机内核的真实 `AF_QIPCRTR` 支持，上游模拟器不会模拟这层传输。
工作流先加载 `qrtr`，用原生 GLib 探针确认一次完整的总线查询，再下载镜像。
ARM64 chroot 内也先检查同一条传输路径；模拟器启动后必须实际查到 SSC 服务 400，
才运行两个未跳过的加速度计回归测试。UMockdev 内部会再次探测并打印底层错误。
环境不满足时会停止，并在日志中区分 socket、总线查询和服务注册失败；
若 runner 内核没有所需模块，可通过 `LIUQIN_IMAGE_RUNNER` 选择已配置 QRTR 的 Linux x86-64 构建机。
参考 [上游 libssc 测试和环境要求](https://codeberg.org/DylanVanAssche/libssc/src/commit/0cf77b93b55752da34dca2dcecc06fca8665184b/README.md)。

## 产物

- `liuqin-os3-candidate-*`：匹配的 Ubuntu boot、installer、rootfs、安装脚本和校验清单。
- `liuqin-os3-android-boot-*`：基于 OS3 原厂 boot 生成的 KernelSU boot 和补丁报告；
  它用于安装器的 `--android-boot`，不要当作 Ubuntu boot。
- `liuqin-os3-logs-*`：构建日志和输入身份，失败时也尽量保留。

Artifacts 保留 7 天。双系统安装仍需另行提供同版本完整原厂 ROM；
候选包没有标记为 `DEVICE_TESTED`，后续有人值守的试装需显式使用 `--allow-unverified`。
