##
#  Copyright (c) 2011 - 2022, ARM Limited. All rights reserved.
#  Copyright (c) 2014, Linaro Limited. All rights reserved.
#  Copyright (c) 2015 - 2020, Intel Corporation. All rights reserved.
#  Copyright (c) 2018, Bingxing Wang. All rights reserved.
#  Copyright (c) Microsoft Corporation.
#
#  SPDX-License-Identifier: BSD-2-Clause-Patent
##

################################################################################
#
# Defines Section - statements that will be processed to create a Makefile.
#
################################################################################
[Defines]
  PLATFORM_NAME                  = tb520fu
  PLATFORM_GUID                  = C06B5DBF-9252-5360-8B65-751D96FC76CD
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/tb520fuPkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = RELEASE|DEBUG
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = tb520fuPkg/tb520fu.fdf
  USE_CUSTOM_DISPLAY_DRIVER      = 1

  #
  # 0 = SM8650-AA
  # 1 = SM8650-Q-AA
  #
  SOC_TYPE                       = 0

!include LanaiPkg/LanaiPkg.dsc.inc

[PcdsFixedAtBuild]
  #
  # DDR Memory
  #
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80000000

  #
  # UEFI Stack
  #
  gArmPlatformTokenSpaceGuid.PcdCPUCoresStackBase|0xA760D000
  gArmPlatformTokenSpaceGuid.PcdCPUCorePrimaryStackSize|0x40000

  #
  # SMBIOS
  #
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemManufacturer|"Lenovo"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"Yoga Tab Plus TB520FU"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailModel|"tb520fu"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"Yoga Tab Plus TB520FU"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"Yoga Tab Plus TB520FU"

  #
  # Simple Frame Buffer
  #
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferWidth|2944
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferHeight|1840
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferColorDepth|32

  #
  # Platform PEI
  #
  gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"

[LibraryClasses]
  SerialPortLib|tb520fuPkg/Library/Tb520fuSerialPortLib/FrameBufferSerialPortLib.inf
  #
  # Memory Libraries
  #
  MemoryMapLib|tb520fuPkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|tb520fuPkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

[Components]
  SiliciumPkg/Drivers/SimpleFbDxe/SimpleFbDxe.inf
  # Linux uses the selected external TB520FU DTB; no foreign ACPI tables.
