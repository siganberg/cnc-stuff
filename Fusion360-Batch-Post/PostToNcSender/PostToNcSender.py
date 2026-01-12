#Author-Francis Marasigan (based on Tim Paterson's PostProcessAll)
#Description-Post process all CAM setups and upload directly to ncSender

import adsk.core, adsk.fusion, adsk.cam, traceback, shutil, json, os, os.path, time, re, pathlib, enum, tempfile, urllib.request, urllib.error

# Version number of settings as saved in documents and settings file
# update this whenever settings content changes
version = 9

# Initial default values of settings
defaultSettings = {
    "version" : version,
    "post" : "",
    "units" : adsk.cam.PostOutputUnitOptions.DocumentUnitsOutput,
    "host" : "ncsender",
    "port" : 8090,
    "outputFolder" : "",
    "sequence" : True,
    "twoDigits" : False,
    "splitSetup" : False,
    "fastZ" : False,
    "toolChange" : "M9 G30",
    "fileExt" : ".nc",
    "numericName" : False,
    "endCodes" : "M5 M9 M30",
    "onlySelected" : False,
    # Groups are expanded or not
    "groupConnection" : True,
    "groupPersonal" : True,
    "groupPost" : True,
    "groupAdvanced" : False,
    # Retry policy
    "initialDelay" : 0.2,
    "postRetries" : 3
}

# Constants - ONLY THESE ARE CHANGED
constCmdName = "Post to ncSender"
constCmdDefId = "PatersonTech_PostToNcSender"
constCAMWorkspaceId = "CAMEnvironment"
constCAMActionsPanelId = "CAMActionPanel"
constPostProcessControlId = "IronPostProcess"
constCAMProductId = "CAMProductType"
constAttrGroup = constCmdDefId
constAttrName = "settings"
constSettingsFileExt = ".settings"
constPostLoopDelay = 0.1
constBodyTmpFile = "gcodeBody"
constOpTmpFile = "8910"   # in case name must be numeric
constRapidZgcode = 'G00 Z{} (Changed from: "{}")\n'
constRapidXYgcode = 'G00 {} (Changed from: "{}")\n'
constFeedZgcode = 'G01 Z{} F{} (Changed from: "{}")\n'
constFeedXYgcode = 'G01 {} F{} (Changed from: "{}")\n'
constFeedXYZgcode = 'G01 {} Z{} F{} (Changed from: "{}")\n'
constAddFeedGcode = " F{} (Feed rate added)\n"
constMotionGcodeSet = {0,1,2,3,33,38,73,76,80,81,82,84,85,86,87,88,89}
constHomeGcodeSet = {28, 30}
constLineNumInc = 5

# Tool tip text
toolTip = (
    "Post process all setups into G-code for your machine.\n\n"
    "The name of the setup is used for the name of the output "
    "file adding the .nc extension. A colon (':') in the name indicates "
    "the preceding portion is the name of a subfolder. Multiple "
    "colons can be used to nest subfolders. Spaces around colons "
    "are removed.\n\n"
    "Setups within a folder are optionally preceded by a "
    "sequence number. This identifies the order in which the "
    "setups appear. The sequence numbers for each folder begin "
    "with 1."
    )

# Global list to keep all event handlers in scope.
# This is only needed with Python.
handlers = []

# Global settingsMgr object
settingsMgr = None

def run(context):
    global settingsMgr
    ui = None
    try:
        settingsMgr = SettingsManager()
        app = adsk.core.Application.get()
        ui  = app.userInterface
        InitAddIn()

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


class SettingsManager:
    def __init__(self):
        self.default = None
        self.path = None
        self.fMustSave = False
        self.inputs = None

    def GetSettings(self, docAttr):
        docSettings = None
        attr = docAttr.itemByName(constAttrGroup, constAttrName)
        if attr:
            try:
                docSettings = json.loads(attr.value)
                if docSettings["version"] == version:
                    return docSettings
            except Exception:
                pass

        # Document does not have valid settings, get defaults
        if not self.default:
            # Haven't read the settings file yet
            file = None
            try:
                file = open(self.GetPath())
                self.default = json.load(file)
                # never allow delFiles or delFolder to default to True
                self.default["delFiles"] = False
                self.default["delFolder"] = False
                if self.default["version"] != version:
                    self.UpdateSettings(defaultSettings, self.default)
            except Exception:
                self.default = dict(defaultSettings)
                self.fMustSave = True
            finally:
                if file:
                    file.close

        if not docSettings:
            docSettings = dict(self.default)
        else:
            self.UpdateSettings(self.default, docSettings)
        return docSettings

    def SaveDefault(self, docSettings):
        self.fMustSave = False
        self.default = dict(docSettings)
        # never allow delFiles or delFolder to default to True
        self.default["delFiles"] = False
        self.default["delFolder"] = False
        try:
            strSettings = json.dumps(docSettings)
            file = open(self.GetPath(), "w")
            file.write(strSettings)
            file.close
        except Exception:
            pass

    def SaveSettings(self, docAttr, docSettings):
        if self.fMustSave:
            self.SaveDefault(docSettings)
        docAttr.add(constAttrGroup, constAttrName, json.dumps(docSettings))

    def UpdateSettings(self, src, dst):
        if "homeEndsOp" in dst:
            if dst["homeEndsOp"] and not ("endCodes" in dst):
                dst["endCodes"] = "M5 M9 M30 G28 G30"
            del dst["homeEndsOp"]
        for item in src:
            if not (item in dst):
                dst[item] = src[item]
        dst["version"] = src["version"]

    def GetPath(self):
        if not self.path:
            pos = __file__.rfind(".")
            if pos == -1:
                pos = len(__file__)
            self.path = __file__[0:pos] + constSettingsFileExt
        return self.path


def InitAddIn():
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface

        # Create a button command definition.
        cmdDefs = ui.commandDefinitions
        cmdDef = cmdDefs.addButtonDefinition(constCmdDefId, constCmdName, toolTip, "resources/Command")

        # Connect to the commandCreated event.
        commandEventHandler = CommandEventHandler()
        cmdDef.commandCreated.add(commandEventHandler)
        handlers.append(commandEventHandler)

        # Get the Actions panel in the Manufacture workspace.
        workSpace = ui.workspaces.itemById(constCAMWorkspaceId)
        addInsPanel = workSpace.toolbarPanels.itemById(constCAMActionsPanelId)

        # Add the button right after the Post Process command.
        cmdControl = addInsPanel.controls.addCommand(cmdDef, constPostProcessControlId, False)
        cmdControl.isPromotedByDefault = True
        cmdControl.isPromoted = True

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def CountOutputFolderFiles(folder, limit, fileExt):
    cntFiles = 0
    cntNcFiles = 0
    for path, dirs, files in os.walk(folder):
        for file in files:
            if file.endswith(fileExt):
                cntNcFiles += 1
            else:
                cntFiles += 1
        if cntFiles > limit:
            return "many files that are not G-code"
        if cntNcFiles > limit * 1.5:
            return "many more G-code files than are produced by this design"
    return None


# Event handler for the commandCreated event.
class CommandEventHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandCreatedEventArgs.cast(args)
            cmd = eventArgs.command

            # Get document attributes that will set initial values
            app = adsk.core.Application.get()
            docSettings  = settingsMgr.GetSettings(app.activeDocument.attributes)

            # See if we're doing only selected setups
            selectedSetups = list()
            product = app.activeDocument.products.itemByProductType(constCAMProductId)
            if product != None:
                for setup in product.setups:
                    if setup.isSelected:
                        selectedSetups.append(setup)

            # Add inputs that will appear in a dialog
            inputs = cmd.commandInputs

            # ncSender connection
            inputGroup = inputs.addGroupCommandInput("groupConnection", "ncSender Connection")
            input = inputGroup.children.addStringValueInput("host", "Host / IP Address", docSettings["host"])
            input.tooltip = "ncSender Host or IP Address"

            input = inputGroup.children.addIntegerSpinnerCommandInput("port", "Port", 1, 65535, 1, docSettings["port"])
            input.tooltip = "ncSender Port"

            input = inputGroup.children.addTextBoxCommandInput("folderLabel", "", "Save to folder (optional):", 1, True)
            input.isFullWidth = True

            input = inputGroup.children.addStringValueInput("outputFolder", "", docSettings.get("outputFolder", ""))
            input.tooltip = "Optional: Save G-code files to this folder"
            input.tooltipDescription = "If specified, G-code files will also be saved to this folder. Leave empty to only upload to ncSender."
            input.isFullWidth = True

            input = inputGroup.children.addBoolValueInput("browseFolder", "Browse", False)
            input.resourceFolder = "resources/Browse"
            input.tooltip = "Browse for Output Folder"

            inputGroup.isExpanded = docSettings["groupConnection"]

            # check box to use only selected setups
            input = inputs.addBoolValueInput("onlySelected",
                                             "Only selected setups",
                                             True,
                                             "",
                                             docSettings["onlySelected"])
            input.tooltip = "Only Process Selected Setups"
            input.tooltipDescription = (
                "Only setups selected in the browser will be processed. Note "
                "that a selected setup will be highlighted, not simply activated. "
                "Selecting individual operations within a setup has no effect."
            )
            input.isEnabled = len(selectedSetups) != 0

            # check box to prepend sequence numbers
            input = inputs.addBoolValueInput("sequence",
                                             "Prepend sequence number",
                                             True,
                                             "",
                                             docSettings["sequence"])
            input.tooltip = "Add Sequence Numbers to Name"

            # check box to select 2-digit sequence numbers
            input = inputs.addBoolValueInput("twoDigits",
                                             "Use 2-digit numbers",
                                             True,
                                             "",
                                             docSettings["twoDigits"])
            input.isEnabled = docSettings["sequence"]
            input.tooltip = "Use 2-Digit Sequence Numbers"

            # select units
            input = inputs.addDropDownCommandInput("units",
                                                   "Post output units",
                                                   adsk.core.DropDownStyles.TextListDropDownStyle)
            input.listItems.add('Document units', True)
            input.listItems.add('Inches', False)
            input.listItems.add('Milimeters', False)
            input.listItems.item(docSettings["units"]).isSelected = True
            input.isFullWidth = True
            input.tooltip = "Post Output Units"

            # "Personal Use" version
            inputGroup = inputs.addGroupCommandInput("groupPersonal", "Personal Use")
            input = inputGroup.children.addBoolValueInput("splitSetup",
                                                          "Use individual operations",
                                                          True,
                                                          "",
                                                          docSettings["splitSetup"])
            input.tooltip = "Split Setup Into Individual Operations"

            input = inputGroup.children.addTextBoxCommandInput("toolLabel",
                                                               "",
                                                               "G-code for tool change:",
                                                               1,
                                                               True)
            input.isFullWidth = True
            label = input

            input = inputGroup.children.addStringValueInput("toolChange", "", docSettings["toolChange"])
            input.isEnabled = docSettings["splitSetup"]
            input.isFullWidth = True
            input.tooltip = "G-code to Precede Tool Change"
            label.tooltip = input.tooltip

            input = inputGroup.children.addTextBoxCommandInput("endLabel",
                                                               "",
                                                               "G-codes that mark ending sequence:",
                                                               1,
                                                               True)
            input.isFullWidth = True
            label = input

            input = inputGroup.children.addStringValueInput("endCodes", "", docSettings["endCodes"])
            input.isEnabled = docSettings["splitSetup"]
            input.isFullWidth = True
            input.tooltip = "G-codes That Mark the Ending Sequence"
            label.tooltip = input.tooltip

            input = inputGroup.children.addBoolValueInput("fastZ",
                                                          "Restore rapid moves",
                                                          True,
                                                          "",
                                                          docSettings["fastZ"])
            input.isEnabled = docSettings["splitSetup"]
            input.tooltip = "Restore Rapid Moves (Experimental)"

            inputGroup.isExpanded = docSettings["groupPersonal"]

            # Advanced -- retry settings
            inputGroup = inputs.addGroupCommandInput("groupAdvanced", "Advanced")
            input = inputGroup.children.addFloatSpinnerCommandInput("initialDelay",
                "Initial time allowance", "s", 0.1, 1.0, 0.1, docSettings["initialDelay"])
            input.tooltip = "Initial Time to Post Process an Operation"
            input = inputGroup.children.addIntegerSpinnerCommandInput("postRetries",
                "Number of retries", 1, 9, 1, docSettings["postRetries"])
            input.tooltip = "Number of Retries"
            inputGroup.isExpanded = docSettings["groupAdvanced"]

            # post processor
            inputGroup = inputs.addGroupCommandInput("groupPost", "Post Processor")
            input = inputGroup.children.addStringValueInput("post", "", docSettings["post"])
            input.isFullWidth = True
            input.tooltip = "Post Processor"

            input = inputGroup.children.addBoolValueInput("browsePost", "Browse", False)
            input.resourceFolder = "resources/Browse"
            input.tooltip = "Browse for Post Processor"
            inputGroup.isExpanded = docSettings["groupPost"]

            input = inputGroup.children.addBoolValueInput("numericName",
                                                          "Name must be numeric",
                                                          True,
                                                          "",
                                                          docSettings["numericName"])
            input.tooltip = "Output File Name Must Be Numeric"

            input = inputGroup.children.addStringValueInput("fileExt", "Output file extension", docSettings["fileExt"])
            input.tooltip = "Output File Extension"

            # button to save default settings
            input = inputs.addBoolValueInput("save", "Save as default", False)
            input.resourceFolder = "resources/Save"
            input.tooltip = "Save These Settings as System Default"

            # text box for error messages
            input = inputs.addTextBoxCommandInput("error", "", "", 3, True)
            input.isFullWidth = True
            input.isVisible = False

            # Connect to the inputChanged event.
            onInputChanged = CommandInputChangedHandler(docSettings)
            cmd.inputChanged.add(onInputChanged)
            handlers.append(onInputChanged)

            # Connect to the validateInputs event.
            onValidateInputs = CommandValidateInputsHandler()
            cmd.validateInputs.add(onValidateInputs)
            handlers.append(onValidateInputs)

            # Connect to the execute event.
            onExecute = CommandExecuteHandler(docSettings, selectedSetups)
            cmd.execute.add(onExecute)
            handlers.append(onExecute)
        except:
            ui = app.userInterface
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# Event handler for the inputChanged event.
class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self, docSettings):
        self.docSettings = docSettings
        super().__init__()

    def notify(self, args):
        app = adsk.core.Application.get()
        ui  = app.userInterface
        try:
            eventArgs = adsk.core.InputChangedEventArgs.cast(args)
            inputs = eventArgs.inputs

            doc = app.activeDocument
            product = doc.products.itemByProductType(constCAMProductId)

            input = eventArgs.input
            if input.id == "save":
                settingsMgr.SaveDefault(self.docSettings)

            elif input.id == "browsePost":
                dialog = ui.createFileDialog()
                post = self.docSettings["post"]
                if len(post) != 0:
                    dialog.initialFilename = post
                else:
                    dialog.initialDirectory = product.genericPostFolder

                dialog.filter = "post processors (*.cps);;All files (*.*)"
                dialog.title = "Select post processor"
                if dialog.showOpen() == adsk.core.DialogResults.DialogOK:
                    self.docSettings["post"] = dialog.filename
                    inputs.itemById("post").value = dialog.filename

            elif input.id == "browseFolder":
                dialog = ui.createFolderDialog()
                dialog.initialDirectory = self.docSettings["outputFolder"]
                dialog.title = "Select output folder (optional)"
                if dialog.showDialog() == adsk.core.DialogResults.DialogOK:
                    self.docSettings["outputFolder"] = dialog.folder
                    inputs.itemById("outputFolder").value = dialog.folder

            elif input.id == "units":
                self.docSettings[input.id] = input.selectedItem.index

            elif input.id in self.docSettings:
                if input.objectType == adsk.core.GroupCommandInput.classType():
                    self.docSettings[input.id] = input.isExpanded
                else:
                    self.docSettings[input.id] = input.value

            if input.id == "sequence":
                inputs.itemById("twoDigits").isEnabled = input.value

            if input.id == "splitSetup":
                inputs.itemById("toolChange").isEnabled = input.value
                inputs.itemById("toolLabel").isEnabled = input.value
                inputs.itemById("endCodes").isEnabled = input.value
                inputs.itemById("endLabel").isEnabled = input.value
                inputs.itemById("fastZ").isEnabled = input.value

        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


# Event handler for the validateInputs event.
class CommandValidateInputsHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        app = adsk.core.Application.get()
        ui  = app.userInterface
        try:
            eventArgs = adsk.core.ValidateInputsEventArgs.cast(args)
            inputs = eventArgs.firingEvent.sender.commandInputs

            post = inputs.itemById("post").value
            fIsPostValid = post.endswith(".cps") and os.path.isfile(post)
            eventArgs.areInputsValid = fIsPostValid
            error = inputs.itemById("error")
            error.isVisible = not eventArgs.areInputsValid
            if not eventArgs.areInputsValid:
                inputs.itemById("groupPost").isExpanded = True
                error.formattedText = "<b>Please select a valid post processor.</b>"
        except:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


# Event handler for the execute event.
class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self, docSettings, selectedSetups):
        self.docSettings = docSettings
        self.selectedSetups = selectedSetups
        super().__init__()

    def notify(self, args):
        eventArgs = adsk.core.CommandEventArgs.cast(args)
        PerformPostProcess(self.docSettings, self.selectedSetups)


def stop(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface

        cmdDef = ui.commandDefinitions.itemById(constCmdDefId)
        if cmdDef:
            cmdDef.deleteMe()

        addinsPanel = ui.allToolbarPanels.itemById(constCAMActionsPanelId)
        cmdControl = addinsPanel.controls.itemById(constCmdDefId)
        if cmdControl:
            cmdControl.deleteMe()
    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))


def upload_to_ncsender(filepath, host="ncsender", port=8090):
    """Upload a G-code file to ncSender. Returns file ID on success, raises Exception on error."""
    filename = os.path.basename(filepath)
    with open(filepath, 'rb') as f:
        file_content = f.read()

    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/octet-stream\r\n\r\n'
    ).encode('utf-8') + file_content + f'\r\n--{boundary}--\r\n'.encode('utf-8')

    url = f"http://{host}:{port}/api/gcode-files"
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')

    response = urllib.request.urlopen(req, timeout=30)
    result = json.loads(response.read().decode('utf-8'))
    return result.get('id')


def load_file_in_ncsender(file_id, host="ncsender", port=8090):
    """Load a file in ncSender by its ID."""
    url = f"http://{host}:{port}/api/gcode-files/{file_id}/load"
    req = urllib.request.Request(url, method='POST')
    req.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req, timeout=30)


def PerformPostProcess(docSettings, setups):
    ui = None
    progress = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface
        doc = app.activeDocument

        settingsMgr.SaveSettings(doc.attributes, docSettings)

        cntFiles = 0
        cntSkipped = 0
        lstSkipped = ""
        product = doc.products.itemByProductType(constCAMProductId)

        if product != None:
            cam = adsk.cam.CAM.cast(product)
            if len(setups) == 0 or not docSettings["onlySelected"]:
                setups = list()
                for setup in cam.setups:
                    setups.append(setup)
            progress = ui.createProgressDialog()
            progress.isCancelButtonShown = True
            progress.show("Generating toolpaths...", "Beginning toolpath generation", 0, 1)
            progress.progressValue = 1
            progress.progressValue = 0

            if len(setups) != 0 and cam.allOperations.count != 0:
                # Use specified folder or temp folder
                specifiedFolder = docSettings.get("outputFolder", "").strip()
                useOutputFolder = len(specifiedFolder) > 0
                if useOutputFolder:
                    # Convert relative paths to absolute (relative to user's home)
                    if not os.path.isabs(specifiedFolder):
                        specifiedFolder = os.path.join(os.path.expanduser("~"), specifiedFolder)
                    outputFolder = specifiedFolder
                    pathlib.Path(outputFolder).mkdir(parents=True, exist_ok=True)
                else:
                    outputFolder = tempfile.mkdtemp(prefix="ncsender_")

                firstFileId = None  # Track first uploaded file to load it

                genStat = cam.generateAllToolpaths(True)
                if not genStat.isGenerationCompleted:
                    progress.maximumValue = genStat.numberOfOperations
                    progress.message = "Generating toolpath %v of %m"
                    while not genStat.isGenerationCompleted:
                        if progress.wasCancelled:
                            return
                        progress.progressValue = genStat.numberOfCompleted
                        time.sleep(.1)

                progressMsg = "{} files uploaded to ncSender"
                progress.show("Post Processing...", "", 0, len(setups))
                progress.progressValue = 1
                progress.progressValue = 0

                cntSetups = 0
                seqDict = dict()

                for setup in cam.setups:
                    if progress.wasCancelled:
                        break
                    if not setup.isSuppressed and setup.allOperations.count != 0:
                        nameList = setup.name.split(':')
                        setupFolder = outputFolder
                        cnt = len(nameList) - 1
                        i = 0
                        while i < cnt:
                            setupFolder += "/" + nameList[i].strip()
                            i += 1

                        if setupFolder in seqDict:
                            seqDict[setupFolder] += 1
                            if setup not in setups:
                                continue
                        else:
                            seqDict[setupFolder] = 1
                            if setup not in setups:
                                continue

                        fname = nameList[i].strip()
                        if docSettings["sequence"] or docSettings["numericName"]:
                            seq = seqDict[setupFolder]
                            seqStr = str(seq)
                            if docSettings["twoDigits"] and seq < 10:
                                seqStr = "0" + seqStr
                            if docSettings["numericName"]:
                                fname = seqStr
                            else:
                                fname = seqStr + ' ' + fname

                        status = PostProcessSetup(fname, setup, setupFolder, docSettings)
                        if status == None:
                            # Upload to ncSender
                            filepath = setupFolder + "/" + fname + docSettings["fileExt"]
                            try:
                                fileId = upload_to_ncsender(filepath, docSettings["host"], docSettings["port"])
                                if firstFileId is None:
                                    firstFileId = fileId
                                cntFiles += 1
                            except Exception as e:
                                cntSkipped += 1
                                lstSkipped += "\nUpload failed for " + fname + ": " + str(e)
                        else:
                            cntSkipped += 1
                            lstSkipped += "\nFailed on setup " + setup.name + ": " + status

                    cntSetups += 1
                    progress.message = progressMsg.format(cntFiles)
                    progress.progressValue = cntSetups

            progress.hide()

            # Load first file in ncSender
            if firstFileId is not None:
                try:
                    load_file_in_ncsender(firstFileId, docSettings["host"], docSettings["port"])
                except:
                    pass  # Ignore load errors

            # Clean up temp folder (only if not using specified output folder)
            if not useOutputFolder:
                try:
                    shutil.rmtree(outputFolder, True)
                except:
                    pass

        if cntSkipped != 0 or len(lstSkipped) > 0:
            ui.messageBox("{} files uploaded to {}:{}.\nIssues:{}".format(
                cntFiles, docSettings["host"], docSettings["port"], lstSkipped),
                constCmdName,
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.WarningIconType)

        elif cntFiles == 0:
            ui.messageBox('No CAM operations posted',
                constCmdName,
                adsk.core.MessageBoxButtonTypes.OKButtonType,
                adsk.core.MessageBoxIconTypes.WarningIconType)

        else:
            ui.messageBox("{} files uploaded to {}:{}".format(
                cntFiles, docSettings["host"], docSettings["port"]),
                constCmdName)

    except:
        if progress:
            progress.hide()
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

def PostProcessSetup(fname, setup, setupFolder, docSettings):
    ui = None
    fileHead = None
    fileBody = None
    fileOp = None
    retVal = "Fusion 360 reported an exception"

    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface
        doc = app.activeDocument
        product = doc.products.itemByProductType(constCAMProductId)
        cam = adsk.cam.CAM.cast(product)

        opName = fname
        opFolder = setupFolder
        if docSettings["splitSetup"]:
            opName = constOpTmpFile
            opFolder = tempfile.gettempdir()
        postInput = adsk.cam.PostProcessInput.create(opName,
                                                    docSettings["post"],
                                                    opFolder,
                                                    docSettings["units"])
        postInput.isOpenInEditor = False

        if not docSettings["splitSetup"]:
            try:
                if not cam.postProcess(setup, postInput):
                    return "Fusion 360 reported an error."
                time.sleep(constPostLoopDelay)
                return None
            except Exception as exc:
                retVal += ": " + str(exc)
                return retVal

        # Split setup into individual operations
        path = setupFolder + "/" + fname
        fileExt = docSettings["fileExt"]
        opPath = opFolder + "/" + opName + fileExt
        pathlib.Path(setupFolder).mkdir(parents=True, exist_ok=True)
        fileHead = open(path + fileExt, "w")
        fileBody = open(opFolder + "/" + constBodyTmpFile + fileExt, "w")

        personalUseFilter = [
            "When using Fusion for Personal Use",
            "moves is reduced to match the feedrate",
            "which can increase machining time",
            "are available with a Fusion Subscription"
        ]
        fFirst = True
        fBlankOk = False
        lineNum = 10
        regToolComment = re.compile(r"\(T[0-9]+\s")
        fFastZenabled = docSettings["fastZ"]
        regBody = re.compile(r""
            "(?P<N>N[0-9]+ *)?"
            "(?P<line>"
            "(M(?P<M>[0-9]+) *)?"
            "(G(?P<G>[0-9]+) *)?"
            "(T(?P<T>[0-9]+))?"
            ".+)",
            re.IGNORECASE | re.DOTALL)
        toolChange = docSettings["toolChange"]
        fToolChangeNum = False
        if len(toolChange) != 0:
            toolChange = toolChange.replace(":", "\n")
            match = regBody.match(toolChange).groupdict()
            if match["N"] != None:
                fToolChangeNum = True
                toolChange = match["line"]
                toolChange = toolChange.splitlines(True)
        endCodes = docSettings["endCodes"]
        endGcodes = re.findall("G([0-9]+)", endCodes)
        endGcodeSet = set()
        for code in endGcodes:
            endGcodeSet.add(int(code))
        endMcodes = re.findall("M([0-9]+)", endCodes)
        endMcodeSet = set()
        for code in endMcodes:
            endMcodeSet.add(int(code))

        if fFastZenabled:
            regParseLine = re.compile(r""
                "(G(?P<G>[0-9]+(\.[0-9]*)?)[^XYZF]*)?"
                "(?P<XY>((X-?[0-9]+(\.[0-9]*)?)[^XYZF]*)?"
                "((Y-?[0-9]+(\.[0-9]*)?)[^XYZF]*)?)"
                "(Z(?P<Z>-?[0-9]+(\.[0-9]*)?)[^XYZF]*)?"
                "(F(?P<F>-?[0-9]+(\.[0-9]*)?)[^XYZF]*)?",
                re.IGNORECASE)
            regGcodes = re.compile(r"G([0-9]+(?:\.[0-9]*)?)")

        i = 0
        ops = setup.allOperations
        while i < ops.count:
            op = ops[i]
            i += 1
            if op.isSuppressed:
                continue

            opHasTool = None
            hasTool = op.hasToolpath
            if hasTool:
                opHasTool = op
            opList = adsk.core.ObjectCollection.create()
            opList.add(op)
            while i < ops.count:
                op = ops[i]
                if op.isSuppressed:
                    i += 1
                    continue
                if op.hasToolpath:
                    if not hasTool:
                        opList.add(op)
                        opHasTool = op
                        i += 1
                    break
                opList.add(op)
                i += 1

            retries = docSettings["postRetries"]
            delay = docSettings["initialDelay"]
            while True:
                try:
                    if not cam.postProcess(opList, postInput):
                        retVal = "Fusion 360 reported an error processing operation"
                        if (opHasTool != None):
                            retVal += ": " +  opHasTool.name
                        return retVal
                except Exception as exc:
                    if (opHasTool != None):
                        retVal += " in operation " +  opHasTool.name
                    retVal += ": " + str(exc)
                    return retVal

                time.sleep(delay)
                try:
                    fileOp = open(opPath, encoding="utf8", errors='replace')
                    break
                except:
                    delay *= 2
                    retries -= 1
                    if retries > 0:
                        continue
                    for file in os.listdir(opFolder):
                        if file.startswith(opName):
                            ext = file[len(opName):]
                            if ext != fileExt:
                                ui.messageBox("Unable to open output file. "
                                    "Found the file with extension '{}' instead "
                                    "of '{}'. Make sure you have the correct file "
                                    "extension set in the Post Process All "
                                    "dialog.".format(ext, fileExt))
                            break
                    return "Unable to open " + opPath

            if not fFirst and fBlankOk:
                fileBody.write("\n")

            line = fileOp.readline()
            if line[0] == "%":
                if fFirst:
                    fileHead.write(line)
                line = fileOp.readline()

            while line[0] == "(" or line[0] == "O" or line[0] == "\n":
                if line[0] == "\n":
                    fBlankOk = True
                if any(phrase in line for phrase in personalUseFilter):
                    line = fileOp.readline()
                    continue
                if regToolComment.match(line) != None:
                    fileHead.write(line)
                    line = fileOp.readline()
                    break

                if fFirst:
                    pos = line.upper().find(opName.upper())
                    if pos != -1:
                        pos += len(opName)
                        if docSettings["numericName"]:
                            fill = "0" * (pos - len(fname) - 1)
                        else:
                            fill = ""
                        line = line[0] + fill + fname + line[pos:]
                    fileHead.write(line)
                line = fileOp.readline()

            fBody = False
            while True:
                match = regBody.match(line).groupdict()
                line = match["line"]
                fNum = match["N"] != None
                if (fBody):
                    break
                toolCur = match["T"]
                if (toolCur != None):
                    if len(toolChange) != 0:
                        processor = post = docSettings["post"].lower()
                        if "masso-rapidchangeatc" in processor:
                            fileBody.write("N" + str(lineNum) + " M98 P63" + toolCur)
                        elif "masso" in processor:
                            fileBody.write("N" + str(lineNum) + " " + line.replace('\n', ''))
                        elif "grbl" in processor:
                            fileBody.write("M6 T" + toolCur)
                        else:
                            fileBody.write("M6 T" + toolCur)
                    else:
                        fBody = True
                        line = fileOp.readline()
                        continue
                    break
                if fFirst or line[0] == "(":
                    if not any(phrase in line for phrase in personalUseFilter):
                        if (fNum):
                            fileBody.write("N" + str(lineNum) + " ")
                            lineNum += constLineNumInc
                        fileBody.write(line)
                line = fileOp.readline()
                if len(line) == 0:
                    return "Tool change G-code (Txx) not found; this post processor is not compatible with Post Process All."
                if line[0] == "\n":
                    fBlankOk = True

            fFastZ = fFastZenabled
            Gcode = None
            Zcur = None
            Zfeed = None
            fZfeedNotSet = True
            feedCur = 0
            fNeedFeed = False
            fLockSpeed = False

            while True:
                endMark = match["M"]
                if endMark != None:
                    endMark = int(endMark)
                    if endMark in endMcodeSet:
                        break
                    if endMark == 49:
                        fLockSpeed = True
                    elif endMark == 48:
                        fLockSpeed = False
                endMark = match["G"]
                if endMark != None:
                    endMark = int(endMark)
                    if endMark in endGcodeSet:
                        break

                if fFastZ:
                    match = regParseLine.match(line)
                    if match.end() != 0:
                        try:
                            match = match.groupdict()
                            Gcodes = regGcodes.findall(line)
                            fNoMotionGcode = True
                            fHomeGcode = False
                            for GcodeTmp in Gcodes:
                                GcodeTmp = int(float(GcodeTmp))
                                if GcodeTmp in constHomeGcodeSet:
                                    fHomeGcode = True
                                    break
                                if GcodeTmp in constMotionGcodeSet:
                                    fNoMotionGcode = False
                                    Gcode = GcodeTmp
                                    if Gcode == 0:
                                        fNeedFeed = False
                                    break

                            if not fHomeGcode:
                                Ztmp = match["Z"]
                                if Ztmp != None:
                                    Zlast = Zcur
                                    Zcur = float(Ztmp)
                                feedTmp = match["F"]
                                if feedTmp != None:
                                    feedCur = float(feedTmp)
                                XYcur = match["XY"].rstrip("\n ")
                                if (Zfeed == None or fZfeedNotSet) and (Gcode == 0 or Gcode == 1) and Ztmp != None and len(XYcur) == 0:
                                    if (Zfeed != None):
                                        fZfeedNotSet = False
                                    Zfeed = Zcur
                                    if Gcode != 0:
                                        line = constRapidZgcode.format(Zcur, line[:-1])
                                        fNeedFeed = True
                                        Gcode = 0
                                if Gcode == 1 and not fLockSpeed:
                                    if Ztmp != None:
                                        if len(XYcur) == 0 and (Zcur >= Zlast or Zcur >= Zfeed or feedCur == 0):
                                            line = constRapidZgcode.format(Zcur, line[:-1])
                                            fNeedFeed = True
                                            Gcode = 0
                                    elif Zcur >= Zfeed:
                                        line = constRapidXYgcode.format(XYcur, line[:-1])
                                        fNeedFeed = True
                                        Gcode = 0
                                elif fNeedFeed and fNoMotionGcode:
                                    if Ztmp != None:
                                        if len(XYcur) != 0:
                                            line = constFeedXYZgcode.format(XYcur, Zcur, feedCur, line[:-1])
                                            fNeedFeed = False
                                            Gcode = 1
                                        elif Zcur < Zfeed and Zcur <= Zlast:
                                            line = constFeedZgcode.format(Zcur, feedCur, line[:-1])
                                            fNeedFeed = False
                                            Gcode = 1
                                    elif len(XYcur) != 0 and Zcur < Zfeed:
                                        line = constFeedXYgcode.format(XYcur, feedCur, line[:-1])
                                        fNeedFeed = False
                                        Gcode = 1
                                if (Gcode != 0 and fNeedFeed):
                                    if (feedTmp == None):
                                        line = line[:-1] + constAddFeedGcode.format(feedCur)
                                    fNeedFeed = False
                                if Zcur != None and Zfeed != None and Zcur >= Zfeed and Gcode != None and \
                                    Gcode != 0 and len(XYcur) != 0 and (Ztmp != None or Gcode != 1):
                                    Zfeed = Zcur + 0.001
                        except:
                            fFastZ = False

                match = regBody.match(line).groupdict()
                line = match["line"]
                fNum = match["N"] != None
                toolCur = match["T"]
                if any(phrase in line for phrase in personalUseFilter):
                    lineFull = fileOp.readline()
                    if len(lineFull) == 0:
                        break
                    match = regBody.match(lineFull).groupdict()
                    line = match["line"]
                    fNum = match["N"] != None
                    continue
                if (toolCur == None):
                    if (fNum):
                        fileBody.write("N" + str(lineNum) + " ")
                        lineNum += constLineNumInc
                    fileBody.write(line)
                else:
                    fileBody.write('\n')

                lineFull = fileOp.readline()
                if len(lineFull) == 0:
                    break
                match = regBody.match(lineFull).groupdict()
                line = match["line"]
                fNum = match["N"] != None

            if fFirst:
                tailGcode = lineFull + fileOp.read()
            fFirst = False
            fileOp.close()
            os.remove(fileOp.name)
            fileOp = None

        if len(tailGcode) != 0:
            tailGcode = tailGcode.splitlines(True)
            for code in tailGcode:
                if any(phrase in code for phrase in personalUseFilter):
                    continue
                match = regBody.match(code).groupdict()
                if match["N"] != None:
                    fileBody.write("N" + str(lineNum) + " " + match["line"])
                    lineNum += constLineNumInc
                else:
                    fileBody.write(code)

        fileBody.close()
        fileBody = open(fileBody.name)
        while True:
            block = fileBody.read(10240)
            if len(block) == 0:
                break
            fileHead.write(block)
            block = None
        fileBody.close()
        os.remove(fileBody.name)
        fileBody = None
        fileHead.close()
        fileHead = None

        return None

    except:
        if fileHead:
            try:
                fileHead.close()
                os.remove(fileHead.name)
            except:
                pass
        if fileBody:
            try:
                fileBody.close()
                os.remove(fileBody.name)
            except:
                pass
        if fileOp:
            try:
                fileOp.close()
                os.remove(fileOp.name)
            except:
                pass
        if ui:
            retVal += " " + traceback.format_exc()
        return retVal
