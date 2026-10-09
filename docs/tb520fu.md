# TB520FU: SteamOS ARM 소스 통합

이 포크의 `tb520fu` 브랜치에 Lenovo Yoga Tab Plus / YOGA Pad Pro AI元启
(TB520FU, lapis, SM8650)용 별도 구성을 추가했습니다.
**빌드·DTB/이미지 생성·Linux 부팅은 하지 않았습니다. 동작 확인된 배포판이나 설치 이미지가 아닙니다.**

## 기존 기기와의 분리

- 기존 `make-steamos-sm8350.sh`, `make-steamos-sm8650.sh`, `make-steamos-sm8750.sh`, 공용 스크립트와 기존 기기 오버레이를 수정하지 않았습니다.
- TB520FU는 새 `make-steamos-tb520fu.sh`와 `tb520fu-overlay/`를 사용합니다. 기본 작업 위치는 `/work/tb520fu`이며 기존 `/work/rootfs`를 거부합니다.
- 전용 소유 표시가 없는 기존 루트파일시스템도 재사용하지 않습니다. 커널 출력 역시 TB520FU 출처 표시가 있어야 합니다.
- 순정 펌웨어는 `/usr/lib/firmware/steamos-arm/tb520fu`에 설치하고 TB520FU 부팅 명령에서만 우선 검색합니다. 다른 기기의 공용 Wi-Fi/GPU/VPU 파일을 덮어쓰지 않습니다.
- UCM·코덱 시퀀스는 TB520FU 전용 경로를 사용합니다. 센서·컨트롤러 프로필은 전용 이미지에 설치하며 장치 식별자는 `lenovo,tb520fu`입니다.
- TB520FU 이미지에서 다른 기기의 팬·앰프·TDP·컨트롤러 정책과 공용 SoC OTA/내부 저장소 설치를 비활성화합니다. 이 처리는 기존 기기 이미지에는 적용되지 않습니다.

## 커널·화면·입력

커널 소스는 [linux-tb520fu](https://github.com/wnduddld0513/linux-tb520fu/tree/tb520fu)의
`82214104148ef8c75ed983fa8f7a755733fc1476`으로 고정했습니다. 해당 소스의 전체 패치 series,
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
전체 범위와 남은 작업은 [커널 하드웨어 대조표](https://github.com/wnduddld0513/linux-tb520fu/blob/tb520fu/tb520fu/HARDWARE.md)를 따릅니다.

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
41개를 추출해 소스 준비까지 실행했습니다. **UEFI도 컴파일하지 않았으므로 현재 생성된 boot.img는 없습니다.**
USB 열거·패널 framebuffer 유지·GRUB 진입·Linux 전환은 실기기 검증이 남아 있습니다.

향후 전용 UEFI를 빌드하면 `$STEAMOS_WORK/uefi/output/tb520fu-uefi-boot.img`와 출처 manifest를
이미지 생성기가 검증하여 함께 담습니다. 별도로 확보한 TB520FU 파일을 쓸 때만
`TB520FU_UEFI_BOOT_IMG`와 `TB520FU_UEFI_SHA256`을 지정합니다. 파일이나 출처가 없으면
이미지 제작을 중단합니다. SHA256은 무결성 확인이며 기기 호환성 검증은 아닙니다.
Y700의 reserved-memory 제거 목록, ROCKNIX ABL, 내부 userdata 설치/자동 GPT·슬롯 변경은 적용하지 않습니다.
중간 출력의 `boot/KERNEL`은 기존 루트파일시스템 준비 코드와 연결하기 위한 carrier이며 **기기에 플래시할 boot.img가 아닙니다.**

공용 SoC OTA는 다른 기기 커널과 기존 부팅 레이아웃을 설치하므로 TB520FU 이미지에서 막습니다.
TB520FU 전용 서명·업데이트 manifest 및 복구 절차는 후속 작업입니다. Steam 클라이언트 자체 업데이트와 별개입니다.

## 향후 빌드 절차 — 이번 작업에서는 실행하지 않음

기존 [빌드 환경 준비](building.md)를 먼저 따릅니다. 사용자 공간은 ARM64 Linux 호스트에서
전용 SteamOS 루트파일시스템을 chroot하여 빌드합니다. WSL x86에서는 커널을 크로스 빌드할 수 있지만,
사용자 공간까지 같은 방법으로 바로 빌드할 수 있다는 뜻은 아닙니다.
커널 준비에는 **static ARM64 BusyBox**가 필요합니다. ARM64 호스트에서는 `busybox-static`을 사용할 수 있고,
x86 호스트에서는 ARM64 파일을 `TB520FU_BUSYBOX`로 지정해야 합니다.

```bash
# 새 체크아웃의 push를 이 포크/tb520fu로 제한
bash tools/setup-fork.sh

# 아래는 향후 실행할 빌드 명령이며 이번 변경에서는 실행하지 않음
export STEAMOS_WORK=/work/tb520fu
export TB520FU_SOURCE_DIR=/path/to/clean/linux-tb520fu
# 위 경로는 source.env의 고정 commit과 일치해야 하며 생략하면 고정 소스를 가져옴
bash scripts/build-tb520fu-kernel.sh

# UEFI 빌드 환경은 Mu-Silicium의 LLVM/ARM64 도구·Python 의존성을 별도로 준비
export TB520FU_STOCK_DIR=/path/to/TB520FU-stock/image
bash scripts/build-tb520fu-uefi.sh --build "$TB520FU_STOCK_DIR"

# 기존 프로젝트가 요구하는 gamescope·Box64·InputPlumber 등 빌드 전제도 필요
sudo -E bash make-steamos-tb520fu.sh --prepare-rootfs
sudo -E bash scripts/build-tb520fu-runtime.sh "$STEAMOS_WORK/rootfs"
sudo -E bash make-steamos-tb520fu.sh --image-only
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
