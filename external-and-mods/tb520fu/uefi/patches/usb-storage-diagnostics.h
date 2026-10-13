// SPDX-License-Identifier: BSD-2-Clause-Patent
// Private TB520FU MsBootPolicy include, after IsDevicePathUSB().
#include <Protocol/Usb2HostController.h>
#include <Protocol/UsbIo.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DiskIo.h>

STATIC
VOID
TbUsbShowPath (IN EFI_HANDLE Handle)
{
  EFI_DEVICE_PATH_PROTOCOL *Path;
  CHAR16 *Text;

  Path = DevicePathFromHandle (Handle);
  if (Path == NULL) {
    return;
  }
  Text = ConvertDevicePathToText (Path, TRUE, TRUE);
  if (Text != NULL) {
    DEBUG ((DEBUG_WARN, "TB USB path: %s\n", Text));
    FreePool (Text);
  }
}

STATIC
VOID
TbUsbDiagnostics (VOID)
{
  EFI_HANDLE *Handles;
  UINTN Count, Index, HostControllers, UsbInterfaces, UsbDisks, UsbFilesystems;
  EFI_STATUS Status, ReadStatus;
  EFI_USB_IO_PROTOCOL *Usb;
  EFI_USB_DEVICE_DESCRIPTOR Device;
  EFI_USB_INTERFACE_DESCRIPTOR Interface;
  EFI_BLOCK_IO_PROTOCOL *Block;
  EFI_DISK_IO_PROTOCOL *Disk;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
  EFI_DEVICE_PATH_PROTOCOL *Path;
  EFI_FILE_PROTOCOL *Root, *File;
  UINT8 Sector[512], Header[64];
  UINTN Length;

  DEBUG ((DEBUG_WARN, "TB USB storage scan begin\n"));
  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiUsb2HcProtocolGuid, NULL, &Count, &Handles);
  HostControllers = Count;
  DEBUG ((DEBUG_WARN, "TB USB host controllers=%u status=%r\n", Count, Status));
  if (!EFI_ERROR (Status)) {
    for (Index = 0; Index < Count && Index < 12; Index++) {
      TbUsbShowPath (Handles[Index]);
    }
    FreePool (Handles);
  }

  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiUsbIoProtocolGuid, NULL, &Count, &Handles);
  UsbInterfaces = Count;
  DEBUG ((DEBUG_WARN, "TB USB enumerated interfaces=%u status=%r\n", Count, Status));
  if (!EFI_ERROR (Status)) {
    for (Index = 0; Index < Count && Index < 12; Index++) {
      Status = gBS->HandleProtocol (Handles[Index], &gEfiUsbIoProtocolGuid, (VOID **)&Usb);
      if (EFI_ERROR (Status)) {
        continue;
      }
      ZeroMem (&Device, sizeof (Device));
      ZeroMem (&Interface, sizeof (Interface));
      Status = Usb->UsbGetDeviceDescriptor (Usb, &Device);
      ReadStatus = Usb->UsbGetInterfaceDescriptor (Usb, &Interface);
      DEBUG ((DEBUG_WARN, "TB USB VID:PID=%04x:%04x device=%r interface=%r class=%02x subclass=%02x protocol=%02x\n",
              Device.IdVendor, Device.IdProduct, Status, ReadStatus,
              Interface.InterfaceClass, Interface.InterfaceSubClass, Interface.InterfaceProtocol));
      TbUsbShowPath (Handles[Index]);
    }
    FreePool (Handles);
  }

  UsbDisks = 0;
  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiBlockIoProtocolGuid, NULL, &Count, &Handles);
  if (!EFI_ERROR (Status)) {
    for (Index = 0; Index < Count; Index++) {
      Path = DevicePathFromHandle (Handles[Index]);
      if (Path == NULL || !IsDevicePathUSB (Path)) {
        continue;
      }
      UsbDisks++;
      if (UsbDisks > 12) {
        continue;
      }
      Status = gBS->HandleProtocol (Handles[Index], &gEfiBlockIoProtocolGuid, (VOID **)&Block);
      if (EFI_ERROR (Status) || Block->Media == NULL) {
        continue;
      }
      DEBUG ((DEBUG_WARN, "TB USB disk partition=%u present=%u block=%u last=%lx\n",
              Block->Media->LogicalPartition, Block->Media->MediaPresent,
              Block->Media->BlockSize, Block->Media->LastBlock));
      TbUsbShowPath (Handles[Index]);
      Status = gBS->HandleProtocol (Handles[Index], &gEfiDiskIoProtocolGuid, (VOID **)&Disk);
      if (!EFI_ERROR (Status) && Block->Media->MediaPresent) {
        ZeroMem (Sector, sizeof (Sector));
        Status = Disk->ReadDisk (Disk, Block->Media->MediaId, 0, sizeof (Sector), Sector);
        DEBUG ((DEBUG_WARN, "TB USB sector read=%r signature=%02x%02x partition-type=%02x\n",
                Status, Sector[510], Sector[511], Sector[450]));
      } else {
        DEBUG ((DEBUG_WARN, "TB USB DiskIo=%r\n", Status));
      }
    }
    FreePool (Handles);
  }

  UsbFilesystems = 0;
  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleFileSystemProtocolGuid, NULL, &Count, &Handles);
  if (!EFI_ERROR (Status)) {
    for (Index = 0; Index < Count; Index++) {
      Path = DevicePathFromHandle (Handles[Index]);
      if (Path == NULL || !IsDevicePathUSB (Path)) {
        continue;
      }
      UsbFilesystems++;
      if (UsbFilesystems > 12) {
        continue;
      }
      TbUsbShowPath (Handles[Index]);
      Status = gBS->HandleProtocol (Handles[Index], &gEfiSimpleFileSystemProtocolGuid, (VOID **)&Fs);
      if (EFI_ERROR (Status)) {
        continue;
      }
      Root = NULL;
      Status = Fs->OpenVolume (Fs, &Root);
      DEBUG ((DEBUG_WARN, "TB USB FAT open=%r\n", Status));
      if (!EFI_ERROR (Status)) {
        File = NULL;
        Status = Root->Open (Root, &File, L"\\EFI\\BOOT\\BOOTAA64.EFI", EFI_FILE_MODE_READ, 0);
        DEBUG ((DEBUG_WARN, "TB USB BOOTAA64 open=%r\n", Status));
        if (!EFI_ERROR (Status)) {
          Length = sizeof (Header);
          ZeroMem (Header, sizeof (Header));
          Status = File->Read (File, &Length, Header);
          DEBUG ((DEBUG_WARN, "TB USB BOOTAA64 read=%r bytes=%u magic=%02x%02x\n",
                  Status, Length, Header[0], Header[1]));
          File->Close (File);
        }
        Root->Close (Root);
      }
    }
    FreePool (Handles);
  }
  DEBUG ((DEBUG_WARN, "TB USB scan end: HC=%u interfaces=%u disks=%u filesystems=%u\n",
          HostControllers, UsbInterfaces, UsbDisks, UsbFilesystems));
}
