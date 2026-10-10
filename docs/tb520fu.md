# TB520FU: SteamOS ARM 포트

이 포크의 `tb520fu` 브랜치에 Lenovo Yoga Tab Plus / YOGA Pad Pro AI元启
(TB520FU, lapis, SM8650)용 별도 구성을 추가했습니다.
**커널·모듈·Tianma/BOE DTB·UEFI boot.img·ARM64 런타임·SteamOS USB 이미지 빌드를 완료했습니다. 실기기 Linux 부팅·하드웨어 동작은 아직 확인하지 않았습니다.**

## 생성 파일과 검증

[TB520FU 시험판 다운로드](https://github.com/wnduddld0513/SteamOS-ARM-Port/releases/tag/tb520fu-experimental-20261010) · [빌드 검토 기록](tb520fu-build-review.json)

- `steamos-tb520fu-experimental-20261010.img.7z.001`부터 모든 분할 파일을 같은 디렉터리에 받은 후 첫 파일을 7-Zip으로 풉니다. 내부 파일은 `steamos-tb520fu.img`입니다.
- USB 이미지는 **16,594,763,776바이트**이므로 **32 GB 이상**의 외부 저장 장치가 필요합니다. 이미지와 별도로 전용 `tb520fu-uefi-boot.img`, 커널·모듈 archive, ARM64 런타임 archive, 출처·해시 manifest를 제공합니다.
- 커널 7.2.6, 모듈 1,594개와 두 패널 DTB를 생성했습니다. 터치·밝기·오디오·진동 등 핵심 설정/모듈과 패널별 터치 펌웨어 참조를 확인했습니다.
- ARM64 chroot에서 센서·RPC·IMU bridge·InputPlumber를 컴파일하고 동적 라이브러리 누락을 검사했습니다. `inputplumber --version`은 `0.81.0`, 종료 코드 0으로 실행됐습니다.
- 이미지의 세 파일시스템을 읽기 전용으로 검사했고, 커널·DTB·UEFI 해시, GRUB/fstab UUID, 두 패널 메뉴, 빌드 캐시 제외와 초기 machine-id를 확인했습니다.
- 오디오 토폴로지는 `alsatplg` 종료 코드 0으로 생성됐으나 커널이 제공하는 외부 DAI widget 경고가 있습니다. DSP·스피커·마이크 실동작 확인을 뜻하지 않습니다.

USB 이미지 SHA256: `a463eb599beb0853872dcfe58c6899f36195d6edc5c36a7817d943c9bc56107c`.
분할 파일 및 개별 배포 파일의 해시는 릴리스의 `SHA256SUMS`를 확인합니다. 이번 작업에서 기기에 플래시하거나 재부팅하지 않았습니다.

## 기존 기기와의 분리

- 기존 `make-steamos-sm8350.sh`, `make-steamos-sm8650.sh`, `make-steamos-sm8750.sh`, 공용 스크립트와 기존 기기 오버레이를 수정하지 않았습니다.
- TB520FU는 새 `make-steamos-tb520fu.sh`와 `tb520fu-overlay/`를 사용합니다. 기본 작업 위치는 `/work/tb520fu`이며 기존 `/work/rootfs`를 거부합니다.
- 전용 소유 표시가 없는 기존 루트파일시스템도 재사용하지 않습니다. 커널 출력 역시 TB520FU 출처 표시가 있어야 합니다.
- 순정 펌웨어는 `/usr/lib/firmware/steamos-arm/tb520fu`에 설치하고 TB520FU 부팅 명령에서만 우선 검색합니다. 다른 기기의 공용 Wi-Fi/GPU/VPU 파일을 덮어쓰지 않습니다.
- UCM·코덱 시퀀스는 TB520FU 전용 경로를 사용합니다. 센서·컨트롤러 프로필은 전용 이미지에 설치하며 장치 식별자는 `lenovo,tb520fu`입니다.
- TB520FU 이미지에서 다른 기기의 팬·앰프·TDP·컨트롤러 정책과 공용 SoC OTA/내부 저장소 설치를 비활성화합니다. 이 처리는 기존 기기 이미지에는 적용되지 않습니다.

## 커널·화면·입력

커널 소스는 [linux-tb520fu](https://github.com/wnduddld0513/linux_kernel_lenovo_tb520fu/tree/main)의
`54ed573a816532658f411e0cabf93072740976e2`으로 고정했습니다. 해당 소스의 전체 패치 series,
DT, 설정을 사용하고 SteamOS용 설정과 외부 USB 루트 UUID를 처리하는 initramfs를 더합니다.
내장 DRM의 초기 probing에 필요한 Adreno 마이크로코드와 두 터치 펌웨어도 initramfs에 담습니다.
ROCKNIX/Y700 커널 패치를 이 커널 위에 다시 섞지 않습니다.

| 패널 | DTB | 터치 펌웨어 |
| --- | --- | --- |
| Tianma NT36532 | `sm8650-lenovo-tb520fu.dtb` | `novatek_ts_tianma_fw.bin` |
| BOE NT36532 | `sm8650-lenovo-tb520fu-boe.dtb` | `novatek_ts_boe_fw.bin` |

두 패널 모두 기본 해상도는 **2944×1840**, 현재 구현 주사율은 **120 Hz**입니다.
Game Mode도 120 Hz·가로 방향으로 설정하며 지원하지 않는 60/90/144 Hz를 광고하지 않습니다.
부팅 메뉴 기본값은 Tianma이고 BOE를 별도로 선택할 수 있습니다. 자동 패널 판별은 없습니다.
터치 네 모서리·펜 정렬, HDR/HBM·ESD 복구, 추가 주사율과 절전 복귀는 검증 또는 구현이 남아 있습니다.

Adreno 750/Turnip, Iris, WCN7850, 6개 AW882xx와 WCD9395, USB-C/DP·충전,
pogo 키보드·트랙패드, PM8550B 진동, SSC 센서, NFC·Goodix 제어는 커널 포팅본의 범위를 유지합니다.
G9 컨트롤러는 Steam Deck UHID 대상으로 설정하고, TB520FU IMU 허용 및 Legion 버튼 chord 패치를 포함합니다.

카메라 촬영, 지문 인증, SAR/덮개 정책, 펜 충전 제어 등 미완료 항목은 OS를 바꿔도 완성되지 않습니다.
전체 범위와 남은 작업은 [커널 하드웨어 대조표](https://github.com/wnduddld0513/linux_kernel_lenovo_tb520fu/blob/main/tb520fu/HARDWARE.md)를 따릅니다.

## 로컬 펌웨어·사용자 공간

[출처 고정값](../external-and-mods/tb520fu/source.env)과
[펌웨어 manifest](../external-and-mods/tb520fu/firmware-manifest.json)를 사용합니다.
순정 archive SHA256은 `315f7d7f349fef84fbe05211fbbc55eaad3d93c750326bc80baca6e849da4328`입니다.
274개 파일의 정확한 집합·크기·SHA256을 먼저 검증한 후 설치합니다. 펌웨어 바이너리는 Git에 올리지 않습니다.

커널 저장소에서 준비한 `build_files/firmware-lenovo-tb520fu.tar.gz`를 다음 위치에 두거나
`TB520FU_FIRMWARE`로 지정합니다.

```text
external-and-mods/tb520fu/local/firmware-lenovo-tb520fu.tar.gz
```

센서는 고정된 GUF296 libssc·hexagonrpc·iio-sensor-proxy 소스와 포팅본의 IMU bridge를
**SteamOS/Arch의 libc에 맞춰** 빌드하도록 연결했습니다. Fedora RPM 바이너리를 복사하지 않습니다.
순정 SSC 설정·DSP 라이브러리는 전용 경로로 설치합니다. 공장 센서 registry는 이 태블릿의 persist를
`ro,noload`로 읽어 별도 상태 디렉터리에 복사하며 원본 persist를 수정하지 않습니다.
오디오 토폴로지와 코덱 시퀀스도 출처 commit을 고정하고 TB520FU 경로에 설치합니다.

## 부팅 경로와 현재 한계

USB 이미지의 FAT 파티션에 ARM64 GRUB·Image·두 DTB를 준비합니다. GRUB의 일반 ARM64 프로그램은
기존 프로젝트의 해시 고정 바이너리를 공유하지만, **Y700용 UEFI/boot.img는 가져오지 않습니다.**
전용 UEFI는 [Mu-Silicium TB520FU 포트](../external-and-mods/tb520fu/uefi/README.md)로 추가했습니다.
공개 Mu-Silicium의 SM8650/Lanai 지원을 고정 commit으로 사용하며, 이 태블릿의 순정 `uefi.elf`·
`xbl_config.elf`에서 하드웨어 모듈과 메모리 맵을 추출합니다. 순정 모듈·설정 69개와 메모리 영역
41개를 추출해 전용 UEFI를 컴파일했습니다. Mu 빌드의 이미지 검증 49개가 통과했고, Android v4 헤더·ARM64 BootShim·FV·SHA256을 별도로 확인했습니다.
생성된 `tb520fu-uefi-boot.img`는 1,155,072바이트이며 SHA256은
`41409e12b33cabd3f3488d0f620cd63e8b1deea69263d661da750e6cb1a25bcb`입니다.
USB 열거·패널 framebuffer 유지·GRUB 진입·Linux 전환은 실기기 검증이 남아 있습니다.

전용 UEFI를 직접 빌드하면 `$STEAMOS_WORK/uefi/output/tb520fu-uefi-boot.img`와 출처 manifest를
이미지 생성기가 검증하여 함께 담습니다. 별도로 확보한 TB520FU 파일을 쓸 때만
`TB520FU_UEFI_BOOT_IMG`와 `TB520FU_UEFI_SHA256`을 지정합니다. 로컬 파일이 없으면
[고정된 포크 릴리스](../external-and-mods/tb520fu/uefi/release.env)에서 TB520FU 전용 파일과 출처 manifest를 받습니다. 검증할 파일이나 출처가 없으면 이미지 제작을 중단합니다. SHA256은 무결성 확인이며 기기 호환성 검증은 아닙니다.
Y700의 reserved-memory 제거 목록, ROCKNIX ABL, 내부 userdata 설치/자동 GPT·슬롯 변경은 적용하지 않습니다.
중간 출력의 `boot/KERNEL`은 기존 루트파일시스템 준비 코드와 연결하기 위한 carrier이며 **기기에 플래시할 boot.img가 아닙니다.**

공용 SoC OTA는 다른 기기 커널과 기존 부팅 레이아웃을 설치하므로 TB520FU 이미지에서 막습니다.
TB520FU 전용 서명·업데이트 manifest 및 복구 절차는 후속 작업입니다. Steam 클라이언트 자체 업데이트와 별개입니다.

## 빌드 절차

기존 [빌드 환경 준비](building.md)를 먼저 따릅니다. 사용자 공간은 ARM64 Linux 호스트에서
전용 SteamOS 루트파일시스템을 chroot하여 빌드합니다. WSL x86에서는 커널을 크로스 빌드하고,
사용자 공간은 `qemu-user-static`의 ARM64 binfmt를 등록한 후 같은 루트파일시스템에서 실행합니다.
고정된 Rust 1.90.0 도구 체인과 빌드 전용 호환 라이브러리는 최종 이미지에서 제외합니다.
커널 준비에는 **static ARM64 BusyBox**가 필요합니다. ARM64 호스트에서는 `busybox-static`을 사용할 수 있고,
x86 호스트에서는 ARM64 파일을 `TB520FU_BUSYBOX`로 지정해야 합니다.

```bash
# 새 체크아웃의 push를 이 포크/tb520fu로 제한
bash tools/setup-fork.sh

export STEAMOS_WORK=/work/tb520fu
export TB520FU_SOURCE_DIR=/path/to/clean/linux-tb520fu
# 위 저장소에 source.env의 고정 commit이 있어야 하며 생략하면 고정 소스를 가져옴
# 실제 빌드 파일은 현재 HEAD가 아닌 고정 commit에서 git archive로 추출
bash scripts/build-tb520fu-kernel.sh

# UEFI 빌드 환경은 Mu-Silicium의 LLVM/ARM64 도구·Python 의존성을 별도로 준비
export TB520FU_STOCK_DIR=/path/to/TB520FU-stock/image
bash scripts/build-tb520fu-uefi.sh --build "$TB520FU_STOCK_DIR"

# 공용 SM8650 v1.3.0 사용자 공간을 SHA256 검증 후 가져옴
# gamescope·Box64·Steam 클라이언트 등 공용 프로그램을 재사용하고
# 커널·모듈·펌웨어·센서·입력·오디오·부팅 구성을 TB520FU용으로 교체
sudo -E bash make-steamos-tb520fu.sh --base-release

# 중단 후 전용 루트파일시스템에서 다시 패킹
# sudo -E bash make-steamos-tb520fu.sh --image-only
```

완성 이미지 이름은 기본 `steamos-tb520fu.img`입니다. `TB520FU_PANEL=tianma|boe|both`로 메뉴 구성을
선택하며 기본값은 `both`입니다. 이미지 생성은 연결된 기기에 쓰거나 부트로더를 플래시하지 않습니다.

## 빌드 없는 검토

```bash
python3 tools/check-tb520fu.py
python3 scripts/install-tb520fu.py --check-firmware \
  --firmware external-and-mods/tb520fu/local/firmware-lenovo-tb520fu.tar.gz
```

이 검토는 쉘 문법, Python 구문, TOML/JSON, 원래 기기 파일 유지 및 소스 참조를 확인합니다.
정적 패치 적용은 컴파일을 수행하지 않습니다. 패널 점등·터치·소리·센서·충전·발열·절전이
Linux에서 정상 작동하는지는 별도 실기기 검증이 필요합니다.
