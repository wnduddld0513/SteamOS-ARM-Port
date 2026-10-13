#!/usr/bin/env python3
"""Compile the actual USB diagnostics with real UEFI headers and mock services.
SPDX-License-Identifier: BSD-2-Clause-Patent
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--uefi-prepared", type=Path, required=True)
args = ap.parse_args()
mu = args.uefi_prepared
header = ROOT / "external-and-mods/tb520fu/uefi/patches/usb-storage-diagnostics.h"
assert header.read_bytes() == (mu / "Common/Mu/PcBdsPkg/MsBootPolicy/Tb520fuUsbDiagnostics.h").read_bytes()
source = (mu / "Common/Mu/PcBdsPkg/MsBootPolicy/MsBootPolicy.c").read_text()
retry = source.index("PauseToLetUsbDrivesEnumerateThroughHubs ();", source.index("case MsBootUSB:"))
assert retry < source.index("EfiBootManagerConnectAll ();", retry) < source.index("TbUsbDiagnostics ();", retry)
assert source.index("TbUsbDiagnostics ();", retry) < source.index("SelectAndBootDevice (", retry)

harness = r'''
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#undef NULL
#include <Uefi.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/Usb2HostController.h>
#include <Protocol/UsbIo.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DiskIo.h>
#include <Library/DebugLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>

EFI_GUID gEfiUsb2HcProtocolGuid={1},gEfiUsbIoProtocolGuid={2};
EFI_GUID gEfiBlockIoProtocolGuid={3},gEfiDiskIoProtocolGuid={4};
EFI_GUID gEfiSimpleFileSystemProtocolGuid={5};
static EFI_DEVICE_PATH_PROTOCOL UsbPath,InternalPath;
static EFI_HANDLE Hc=(VOID*)1,Io=(VOID*)2,DiskHandle=(VOID*)3,FsHandle=(VOID*)4,Internal=(VOID*)5;
static EFI_USB_IO_PROTOCOL Usb;
static EFI_BLOCK_IO_MEDIA Media;
static EFI_BLOCK_IO_PROTOCOL Block;
static EFI_DISK_IO_PROTOCOL Disk;
static EFI_SIMPLE_FILE_SYSTEM_PROTOCOL Fs;
static EFI_FILE_PROTOCOL Root,File;
static int Mode,Allocations,Frees,Reads,Volumes,Opens,FileReads,Closes,InternalTouched,Logs,Summaries;
VOID EFIAPI DebugPrint(UINTN Level,CONST CHAR8 *Format,...) {
 Logs++;
 if(strstr(Format,"TB USB scan end:")!=NULL) {
  va_list A;va_start(A,Format);Summaries++;
  for(int I=0;I<4;I++)assert(va_arg(A,UINTN)==(UINTN)(Mode==1?0:1));
  va_end(A);
 }
}
BOOLEAN EFIAPI DebugPrintEnabled(VOID) {return TRUE;}
BOOLEAN EFIAPI DebugPrintLevelEnabled(CONST UINTN Level) {return TRUE;}
VOID EFIAPI FreePool(VOID *P) {Frees++;free(P);}
VOID *EFIAPI ZeroMem(VOID *P,UINTN N) {return memset(P,0,N);}
EFI_DEVICE_PATH_PROTOCOL *EFIAPI DevicePathFromHandle(EFI_HANDLE H) {
 return H==Internal ? &InternalPath : &UsbPath;
}
CHAR16 *EFIAPI ConvertDevicePathToText(CONST EFI_DEVICE_PATH_PROTOCOL *P,BOOLEAN A,BOOLEAN B) {
 CHAR16 *S=malloc(8);Allocations++;memcpy(S,L"USB",8);return S;
}
static BOOLEAN EFIAPI IsDevicePathUSB(EFI_DEVICE_PATH_PROTOCOL *P) {return P==&UsbPath;}
static EFI_STATUS EFIAPI Locate(EFI_LOCATE_SEARCH_TYPE T,EFI_GUID *G,VOID *K,UINTN *N,EFI_HANDLE **H) {
 EFI_HANDLE A[2];UINTN C=0;
 assert(T==ByProtocol && K==NULL);
 if(G==&gEfiUsb2HcProtocolGuid) {if(Mode!=1)A[C++]=Hc;}
 else if(G==&gEfiUsbIoProtocolGuid) {if(Mode!=1)A[C++]=Io;}
 else if(G==&gEfiBlockIoProtocolGuid) {A[C++]=Internal;if(Mode!=1)A[C++]=DiskHandle;}
 else if(G==&gEfiSimpleFileSystemProtocolGuid) {A[C++]=Internal;if(Mode!=1)A[C++]=FsHandle;}
 else assert(0);
 *N=C;*H=NULL;if(!C)return EFI_NOT_FOUND;
 *H=malloc(C*sizeof(**H));Allocations++;memcpy(*H,A,C*sizeof(**H));return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI Protocol(EFI_HANDLE H,EFI_GUID *G,VOID **P) {
 if(H==Internal) {InternalTouched++;assert(0);}
 if(G==&gEfiUsbIoProtocolGuid && H==Io)*P=&Usb;
 else if(G==&gEfiBlockIoProtocolGuid && H==DiskHandle)*P=&Block;
 else if(G==&gEfiDiskIoProtocolGuid && H==DiskHandle)*P=&Disk;
 else if(G==&gEfiSimpleFileSystemProtocolGuid && H==FsHandle)*P=&Fs;
 else assert(0);
 return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI Dev(EFI_USB_IO_PROTOCOL *U,EFI_USB_DEVICE_DESCRIPTOR *D) {
 D->IdVendor=0x1234;D->IdProduct=0x5678;return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI Intf(EFI_USB_IO_PROTOCOL *U,EFI_USB_INTERFACE_DESCRIPTOR *I) {
 I->InterfaceClass=8;I->InterfaceSubClass=6;I->InterfaceProtocol=0x50;return EFI_SUCCESS;
}
static EFI_STATUS EFIAPI ReadDisk(EFI_DISK_IO_PROTOCOL *D,UINT32 Id,UINT64 Off,UINTN N,VOID *P) {
 assert(D==&Disk && Id==42 && Off==0 && N==512);Reads++;
 ((UINT8*)P)[510]=0x55;((UINT8*)P)[511]=0xaa;
 return Mode==2 ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}
static EFI_STATUS EFIAPI Volume(EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *F,EFI_FILE_PROTOCOL **R) {
 Volumes++;*R=&Root;return Mode==2 ? EFI_VOLUME_CORRUPTED : EFI_SUCCESS;
}
static EFI_STATUS EFIAPI Open(EFI_FILE_PROTOCOL *R,EFI_FILE_PROTOCOL **F,CHAR16 *Name,UINT64 ModeValue,UINT64 Attr) {
 assert(R==&Root && ModeValue==EFI_FILE_MODE_READ && Attr==0);
 assert(memcmp(Name,L"\\EFI\\BOOT\\BOOTAA64.EFI",46)==0);
 Opens++;*F=&File;return Mode==3 ? EFI_NOT_FOUND : EFI_SUCCESS;
}
static EFI_STATUS EFIAPI ReadFile(EFI_FILE_PROTOCOL *F,UINTN *N,VOID *P) {
 assert(F==&File && *N==64);FileReads++;memcpy(P,"MZ",2);
 return Mode==4 ? EFI_DEVICE_ERROR : EFI_SUCCESS;
}
static EFI_STATUS EFIAPI Close(EFI_FILE_PROTOCOL *F) {Closes++;return EFI_SUCCESS;}
static EFI_BOOT_SERVICES Services={.LocateHandleBuffer=Locate,.HandleProtocol=Protocol};
EFI_BOOT_SERVICES *gBS=&Services;
#include "HEADER_PATH"
int main(void) {
 Usb.UsbGetDeviceDescriptor=Dev;Usb.UsbGetInterfaceDescriptor=Intf;
 Media.MediaId=42;Media.MediaPresent=TRUE;Media.BlockSize=512;Media.LastBlock=4095;
 Block.Media=&Media;Disk.ReadDisk=ReadDisk;Fs.OpenVolume=Volume;
 Root.Open=Open;Root.Close=Close;File.Read=ReadFile;File.Close=Close;
 for(Mode=0;Mode<5;Mode++) {
  Allocations=Frees=Reads=Volumes=Opens=FileReads=Closes=InternalTouched=Logs=Summaries=0;
  TbUsbDiagnostics();
  assert(Allocations==Frees && !InternalTouched && Logs>0 && Summaries==1);
  if(Mode==1) {assert(!Reads && !Volumes && !Opens && !Closes);continue;}
  assert(Reads==1 && Volumes==1);
  if(Mode==2)assert(!Opens && !FileReads && !Closes);
  else if(Mode==3)assert(Opens==1 && !FileReads && Closes==1);
  else assert(Opens==1 && FileReads==1 && Closes==2);
 }
 return 0;
}
'''.replace("HEADER_PATH", str(header))
with tempfile.TemporaryDirectory() as td:
    c, exe = Path(td) / "test.c", Path(td) / "test"
    c.write_text(harness)
    inc = mu / "Mu_Basecore/MdePkg/Include"
    subprocess.run(["cc", "-std=c11", "-fshort-wchar", "-Wall", "-Wextra",
                    "-Wno-unused-parameter", "-Wno-missing-field-initializers",
                    "-I" + str(inc), "-I" + str(inc / "X64"), str(c), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
print("USB retry ordering and actual diagnostics C passed with real UEFI headers:")
print("USB-only reads, empty devices, disk/FAT/file errors, file closes and allocation cleanup.")
