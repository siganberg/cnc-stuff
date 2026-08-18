# Post to ncSender — Fusion 360 Add-In

Post processes **all** CAM setups in the active Fusion design and uploads the
resulting G-code straight to an [ncSender](https://github.com/siganberg/ncSender)
server over the network — no local output folder, no manual file copying, no USB stick.

The first uploaded file is automatically loaded in ncSender, so you can go from
Fusion to "ready to run" in one click.

Based on Tim Paterson's [PostProcessAll](https://github.com/TimPaterson/Fusion360-Batch-Post).

---

## Requirements

| | |
|---|---|
| Autodesk Fusion | Any current version (Personal or paid). Windows or macOS. |
| ncSender | Running and reachable on your network from the machine running Fusion. |
| Post processor | A `.cps` file on your local disk (e.g. `grbl.cps`). |

The add-in talks to ncSender over plain HTTP on your LAN, so both machines must
be able to reach each other. No credentials are used.

---

## Installation

### 1. Get the files

Download or clone this repository, and locate the folder:

```
Fusion360-Batch-Post/PostToNcSender/
```

The folder must contain at least:

```
PostToNcSender.py
PostToNcSender.manifest
resources/
```

Cloning with Git is recommended so you can pull updates later:

```bash
git clone https://github.com/siganberg/cnc-stuff.git
```

### 2. Put it where Fusion looks for add-ins (recommended)

Copy the whole `PostToNcSender` folder into Fusion's `AddIns` directory:

- **Windows**
  ```
  %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\PostToNcSender
  ```
- **macOS**
  ```
  ~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/PostToNcSender
  ```

> The folder name **must** match the script name — `PostToNcSender` — or Fusion
> will not load it.

Alternatively you can leave the files anywhere on disk (for example inside your
cloned repo) and add that folder manually in the next step.

### 3. Enable it in Fusion

1. Start Fusion (or restart it if it was already running).
2. Go to the **Utilities** tab in the **Manufacture** workspace, or the **Tools**
   tab in the **Design** workspace.
3. Click **Add-Ins** to open the **Scripts and Add-Ins** dialog.
4. Switch to the **Add-Ins** tab.
   - If you copied the folder to the `AddIns` directory, **PostToNcSender**
     already appears under **My Add-Ins**.
   - Otherwise click the green **+** and browse to the folder containing
     `PostToNcSender.py`.
5. Select **PostToNcSender**, tick **Run on Startup**, then click **Run**.

### 4. Find the command

Go to the **Manufacture** workspace and open the **Milling** (or **Turning**) tab.
**Post to ncSender** appears on the toolbar right next to the native **Post Process**
command, and in the **Actions** drop-down menu.

---

## First-time setup

Click **Post to ncSender**. The dialog has these fields:

### ncSender Connection

| Field | Description |
|---|---|
| **Host / IP Address** | Hostname or IP of the ncSender server. Default `ncsender`. Use `ncsender.local` if plain `ncsender` does not resolve, or the raw IP (e.g. `192.168.1.50`). |
| **Port** | ncSender's HTTP port. Default `8090`. |
| **Folder (optional)** | Remote folder on ncSender to create and upload into. Leave blank to upload to the root folder. |

### Options

| Option | Description |
|---|---|
| **Only selected setups** | Post only the setups highlighted in the browser tree. Disabled when no setup is selected. |
| **Only selected operations** | Post only the operations highlighted in the browser tree. Operations selected within the same setup are combined into one file, and setups with no selected operation are skipped. Selecting the setup itself includes all of its operations. Disabled when no operation is selected, and ticked automatically when one is. |
| **Prepend sequence number** | Prefix each file name with its order within its folder (`1 roughing`, `2 finishing`, …). Numbering restarts at 1 in each folder. |
| **Use 2-digit numbers** | Zero-pads sequence numbers below 10 (`01`, `02`, …) so files sort correctly. |

### Post Processor

Click **Browse** and select your `.cps` post processor (for example `grbl.cps`).
This field must be filled in before **OK** is enabled.

### Save as default

Click the **Save** button in the dialog to store the current values as the default
for new designs. Settings are also saved per-design automatically each time you run
the command, so each design remembers its own configuration.

Defaults live in `PostToNcSender.settings` next to the script.

---

## Usage

1. Generate your toolpaths in the **Manufacture** workspace.
2. Click **Post to ncSender**.
3. Confirm the host, port, folder, and post processor, then click **OK**.

The add-in will:

1. Post process every setup (or only the selected ones) into a temporary local folder.
2. Create the remote folder on ncSender, if one was specified.
3. Upload every `.nc` file to ncSender.
4. Load the first uploaded file in ncSender.
5. Delete the temporary local files.

A progress dialog shows toolpath generation, posting, and uploading. **No dialog is
shown on success** — you only get a message box if something failed or if nothing
was posted.

Output files always use the `.nc` extension.

### Subfolders from setup names

A colon (`:`) in a setup name creates a subfolder. Everything to the left of the
colon becomes the folder name; multiple colons nest folders. Spaces around the
colon are stripped.

```
Cover : roughing      ->  Cover/roughing.nc
Cover : finishing     ->  Cover/finishing.nc
Block : first edge    ->  Block/first edge.nc
```

Combined with sequence numbers, that becomes `Cover/1 roughing.nc`,
`Cover/2 finishing.nc`, and so on.

### Fusion for Personal Use

The free version of Fusion refuses to emit tool changes in a single posted file.
This add-in always posts each operation individually and stitches the G-code back
together into one file per setup, so multi-tool setups work without any extra
configuration.

---

## Troubleshooting

**"Connection failed" on upload**
ncSender is not reachable at the configured host/port. Verify from the Fusion
machine:

```bash
curl http://ncsender:8090/api/gcode-files/folders
```

If the hostname does not resolve, try `ncsender.local` or the server's IP address.

**Posting fails or reports an exception**
Run it again — Fusion occasionally has timing issues during post processing that
resolve on a retry.

**The command does not appear on the toolbar**
Reopen **Utilities → Add-Ins**, confirm **PostToNcSender** is listed and running,
and make sure you are in the **Manufacture** workspace on the **Milling** or
**Turning** tab. If it is missing from the list entirely, the containing folder
name probably does not match `PostToNcSender`.

**Settings look wrong or stale**
Delete `PostToNcSender.settings` next to the script; defaults are recreated on the
next run.

---

## ncSender endpoints used

For reference, the add-in calls these ncSender HTTP APIs:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/gcode-files/folders` | Create the remote folder |
| `POST` | `/api/gcode-files/file/save` | Upload a G-code file |
| `POST` | `/api/gcode-files/load` | Load the first uploaded file |

---

## Credits & License

Original `PostProcessAll` add-in by Tim Paterson.
ncSender integration by Francis Marasigan.
See [LICENSE](../LICENSE) in the parent folder.
