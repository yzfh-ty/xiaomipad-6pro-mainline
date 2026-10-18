# OS4 移植包：手动构建全新双系统候选包

## 1. 当前范围

本分支固定支持这一份包：

```text
liuqin-ota_full-OS4.0.2.5.XMYCNXM-user-17.0-f077f083f2-2in1-Root.zip
bytes: 7314416178
sha256: 59b290a7fe6566ac3c03194f64d4a660e3f3ee841a5fedaa9364e5329d5395ce
```

包内属性为 Android 17 / SDK 37。这是所检查的第三方移植包，不按文件名将它认定为小米官方原版。

按全新双系统安装准备，不保留旧 Android、Ubuntu 系统或 Ubuntu 用户数据。本次按用户要求只修改代码和文档，**没有运行编译、测试、Actions 或设备刷写**。原有上游验收结果不适用于这个新 Android 组合。

## 2. Actions 输入框

提交并推送这些修改后，在主项目 Fork 中打开 **Actions → System image → Run workflow → main**：

| 输入 | 填写内容 |
| --- | --- |
| `rom_url` | 上面这份 ZIP 的有效 HTTPS 下载直链，必填 |
| `ubuntu_url` | 可留空；如填写，必须是固定 Ubuntu 26.04 ARM64 ISO 的相同内容镜像 |
| `kernel_repository` | 可留空，默认使用当前仓库所有者的 `linux-sm8450-liuqin` |

`rom_url` 只覆盖下载来源，不改变允许的包身份。不同内容的 ZIP 即使改成同名，也会在长度或 SHA-256 校验处停止。URL 通过环境变量传给程序，不作为 shell 命令拼接；临时签名链接不固定在源码中。

工作流在耗时的依赖安装和组件准备前优先下载 ZIP，再使用缓存，减少短期链接在准备期间过期的问题。链接仍必须在 runner 实际开始下载时有效；15 分钟链接可能在排队时失效，需要届时重新获取。

## 3. 解包和 KernelSU

解包器只复制固定清单中的 9 个输入：

- `boot_official.img` → `images/boot.img`。
- `super.zst` → 解压为 raw `images/super.img`，固定长度 9,126,805,504 字节（8.5 GiB）。
- `firmware-update/` 中配套的 vendor_boot、dtbo、vbmeta、vbmeta_system、modem、Bluetooth 和 DSP 镜像 → 原安装器识别的文件名。

解包器不会执行原包的 Windows / Recovery 脚本，也不提取 `boot_magisk.img`、Magisk、FRP、GPT 或 userdata。

该包未提供 `anti_version.txt`。受保护的基础固件已与原 OS3 anti=1 基线完成零填充归一化比较，版本清单显式记录这项来源，归一化目录据此写入 `anti_version.txt=1`。这不代替安装前的设备防回滚核对，也不把缺失值视为 0。

继续使用原来的 KernelSU v3.3.0 `ksuinit` 和 `android12-5.10` LKM：从非 Magisk 的 `boot_official.img` 打补丁，保持 `5.10.237-Fuutao-Qn_miao` 特调内核、命令行和其余启动块不变。`liuqin_boot_ubuntu` 切换模块不改为 Magisk 版本。

能生成 ramdisk 补丁不等于已经证明 LKM 在特调内核上加载成功。KSU 管理器识别、模块加载和双向切换需要新系统真机验收；这里没有禁用校验或强行替换 Android 内核来掩盖兼容性问题。

Ubuntu 仍使用项目固定的主线内核与板级固件。设备树内容与已审阅基线相同，但新包的 DTB / DTBO 校验仍逐文件执行。传感器路径改为读取当前 ROM 的提取目录，原有配置身份检查继续保留。

## 4. 预期构建产物

- `liuqin-os4-candidate-*`：Ubuntu boot、RAM 安装器、rootfs、安装工具、ROM 清单、原 KSU 切换模块。
- `liuqin-os4-android-boot-*`：新的 Android `boot-ksu.img`、补丁报告和 ROM 清单。
- `liuqin-os4-logs-*`：构建日志与输入身份。

Android ROM 本体不上传到这些产物。安装器和产物保持 `OFFLINE_ASSEMBLED` / `OFFLINE_INSPECTED` 状态，不能标为已经真机验证。

## 5. 按原文档全新安装前的 ROM 准备

完整 ZIP 仍需保留。新安装包会附带 `prepare-rom.py`、`stock-rom.py` 和配套清单。

Linux 安装主机需提供 Python `zstandard` 模块（例如 Ubuntu 的 `python3-zstandard` 软件包）。在候选安装包目录中执行：

```sh
python3 prepare-rom.py \
  --archive /path/to/liuqin-ota_full-OS4.0.2.5.XMYCNXM-user-17.0-f077f083f2-2in1-Root.zip \
  --out /path/to/os4-rom
```

然后沿用原文档流程，把 `--rom-dir` 指向 `/path/to/os4-rom`，把 `--android-boot` 指向本次新产物中的 `boot-ksu.img`。不能复用旧 OS3 KSU 镜像，也不能把原 ZIP 解包目录直接作为归一化后的 ROM 目录。

只在本地准备 ROM、检查设备树的入口也已提供，供之后需要时使用；本次未执行：

```sh
python3 tools/prepare-ci-inputs.py \
  --rom-archive /path/to/the-original-unchanged.zip --rom-only
```

重装前正常移除 Google 账号、关闭屏幕锁并核对激活保护；不要执行原包里的 `FlashWindows.bat` 或 Recovery `update-binary` 代替双系统安装器。
