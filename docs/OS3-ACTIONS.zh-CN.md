# OS3 分支：手动构建完整双系统候选包

本分支将 Android 侧基线改为 **OS3.0.7.0.VMYCNXM / Android 15**。
Ubuntu 仍使用 `kernel/source.json` 固定的主线内核，以及仓库已有的 Ubuntu 板级固件。
没有修改内核源码。Android 新 ROM 中的 DSP 与 Ubuntu 的固定 DSP 固件是两组独立输入。

目前只准备了适配代码和 ROM 身份；未在本地运行测试、编译或执行刷写。
首次完整构建和回归检查交给 Actions。成功产物仍是 `OFFLINE_ASSEMBLED`，不代表通过真机验证。

## 手动运行

1. 打开自己的主项目 Fork，在 **Actions** 中启用工作流。
2. 选择 **System image → Run workflow**，分支选 **os3-actions**。
3. `rom_url` 填写下面这份原厂 Fastboot `.tgz` 的可直连 HTTPS 下载链接。
   不能填网页、Recovery ZIP、网盘分享页或 Windows 本地路径。
4. `ubuntu_url` 可留空；如提供镜像，必须与项目固定的 Ubuntu 26.04 ARM64 ISO 逐字节相同。
5. `kernel_repository` 留空会使用 `你的用户名/linux-sm8450-liuqin`。
   本次对应 `yzfh-ty/linux-sm8450-liuqin`，仍按固定提交构建，而非自动追随分支最新提交。
6. 点击 **Run workflow**。完成后在该次运行的 **Artifacts** 下载候选安装包和 Android boot 附件。

如果 GitHub 页面没有显示新输入，可用已登录的 GitHub CLI 明确选择分支：

```sh
gh workflow run image.yml --repo yzfh-ty/xiaomipad-6pro-mainline \
  --ref os3-actions -f rom_url='https://你的下载源/原厂包.tgz'
```

工作流文件 `image.yml` 已存在于 Fork 的默认分支；手动调度选择本分支的版本。
本流程不自动创建公开 Release，也不自动刷写平板。

## 固定原厂包

```text
liuqin_images_OS3.0.7.0.VMYCNXM_20260514.0000.00_15.0_cn_f57d372b08.tgz
bytes: 7541014730
sha256: 9b33c813b7245ef67b1f55555bb3e769de2f13636e9c04f12bfb3788c5337359
```

下载地址可以变化，文件身份必须相同。工作流校验归档、9 个镜像、anti_version.txt，
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

## 产物

- `liuqin-os3-candidate-*`：匹配的 Ubuntu boot、installer、rootfs、安装脚本和校验清单。
- `liuqin-os3-android-boot-*`：基于 OS3 原厂 boot 生成的 KernelSU boot 和补丁报告；
  它用于安装器的 `--android-boot`，不要当作 Ubuntu boot。
- `liuqin-os3-logs-*`：构建日志和输入身份，失败时也尽量保留。

Artifacts 保留 7 天。双系统安装仍需另行提供同版本完整原厂 ROM；
候选包没有标记为 `DEVICE_TESTED`，后续有人值守的试装需显式使用 `--allow-unverified`。
