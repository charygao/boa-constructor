#----------------------------------------------------------------------
# Name:        Explorer.py
# Purpose:     Controls to explore and initialise different data sources
#
# Author:      Riaan Booysen
#
# Created:     2000/11/02
# RCS-ID:      $Id$
# Copyright:   (c) 1999 - 2002 Riaan Booysen
# Licence:     GPL
#----------------------------------------------------------------------

print 'importing Explorers'

from os import path
import os, sys
import string, time, glob, fnmatch
from types import StringType, ClassType

from wxPython.wx import *

import Preferences, Utils
from Preferences import IS

from Models import EditorHelper

import ExplorerNodes
from ExplorerNodes import TransportError, TransportLoadError, TransportSaveError

class TransportCategoryError(TransportError):
    def __init__(self, msg='', filepath=None):
        TransportError.__init__(self, msg, filepath)
        self.msg = msg
        self.filepath = filepath


    def __str__(self):
        if self.filepath:
            return '%s: %s' % (self.msg, self.filepath)
        else:
            return self.msg


#---Explorer utility functions--------------------------------------------------

# Global reference to container for all transport protocols
# The first Explorer Tree created will define this
# XXX This attribute should move to ExplorerNodes
all_transports = None

def openEx(filename, transports=None):
    prot, category, respath, filename = splitURI(filename)
    if transports is None and all_transports:
        transports = all_transports
    return getTransport(prot, category, respath, transports)

def listdirEx(filepath, extfilter = ''):
    return filter(lambda f, extfilter=extfilter: \
          not extfilter or string.lower(os.path.splitext(f)[1]) == extfilter,
          map(lambda n: n.treename, openEx(filepath).openList()))

# XXX Handle compound URIs by splitting on the first 2 :// and calling
# XXX splitURI again recursively ??
def splitURI(filename):
    protsplit = string.split(filename, '://')
    # check FS (No prot defaults to 'file')
    if len(protsplit) == 1:
        return 'file', '', filename, 'file://'+filename

    elif len(protsplit) == 2:
        prot, filepath = protsplit
        # file://[path] format
        if prot == 'file':
            return prot, '', filepath, filename

        # zope://[category]/<[meta type]>/[path] format
        elif prot == 'zope':
            segs = string.split(filepath, '/')
            if len(segs) < 2:
                raise TransportCategoryError('Category not found', filepath)
            category = segs[0]+'|'+segs[1][1:-1]
            return prot, category, string.join(segs[2:], '/'), filename
        # zopedebug://[host[:post]]/[path]/[meta type]
        # magically maps zopedebug urls to Boa zope uris
        elif prot == 'zopedebug':
            segs = string.split(filepath, '/')
            if len(segs) < 3:
                raise TransportCategoryError('Zope debug path invalid', filepath)
            host, filepath, meta = segs[0], segs[1:-1], segs[-1]
            try:               host, port = string.split(host, ':')
            except ValueError: port = 80
            else:              port = int(port)
            # try to find category that can open this url
            lw = string.lower
            for cat in all_transports.entries:
                if cat.itemProtocol == 'zope':
                    itms = cat.openList()
                    for itm in itms:
                        props = itm.properties
                        if lw(props['host']) == lw(host) and \
                              props['httpport'] == port:
                            filepath = string.join(filepath, '/')
                            name = itm.name or itm.treename
                            return 'zope', '%s|%s' %(name, meta), filepath, \
                                   'zope://%s/<%s>/%s'%(name, meta, filepath)

            raise TransportCategoryError(\
                  'Could not map Zope debug path to defined Zope Category item',
                  filepath)

        # Other transports [prot]://[category]/[path] format
        elif prot == 'reg':
            try:
                category, respath = string.split(filepath, '//', 1)
            except:
                raise
            return prot, category, respath, filename
        else:
            idx = string.find(filepath, '/')
            if idx == -1:
                raise TransportCategoryError('Category not found', filepath)
            else:
                category, respath = filepath[:idx], filepath[idx+1:]
            return prot, category, respath, filename
    # Multiprot URIs
    elif len(protsplit) == 3:
        prot, zipfile, zipentry = protsplit
        if prot == 'zip':
            return prot, zipfile, zipentry, filename
        else:
            raise TransportError('Unhandled protocol: %s'%prot)
    else:
        raise TransportError('Too many protocol separators (://)')

def getTransport(prot, category, respath, transports):
    if prot == 'file':
        for tp in transports.entries:
            if tp.itemProtocol == 'file':
                return tp.getNodeFromPath(respath, forceFolder=false)
        raise TransportError('FileSysCatNode not found in transports %s'\
              %transports.entries)
    elif prot == 'zip':
        from ZipExplorer import ZipFileNode
        zf = ZipFileNode(os.path.basename(category), category, None, -1, None, None)
        zf.openList()
        return zf.getNodeFromPath(respath)
    elif prot == 'zope':
        return findZopeExplorerNode(category, respath, transports)
    elif category:
        return findCatExplorerNode(prot, category, respath, transports)
    else:
        raise TransportError('Unhandled transport', (prot, category, respath))

def findCatExplorerNode(prot, category, respath, transports):
    for cat in transports.entries:
        if hasattr(cat, 'itemProtocol') and cat.itemProtocol == prot:
            itms = cat.openList()
            for itm in itms:
                if itm.name == category or itm.treename == category:
                    # connect if not a stateless protocol
                    #if itm.connection:
                    #    itm.openList()
                    return itm.getNodeFromPath(respath)
    raise TransportError('Catalog transport could not be found: %s || %s'%(category, respath))
#    return None

def findZopeExplorerNode(catandmeta, respath, transports):
    category, metatype = string.split(catandmeta, '|')
    for cat in transports.entries:
        if hasattr(cat, 'itemProtocol') and cat.itemProtocol == 'zope':
            itms = cat.openList()
            for itm in itms:
                if itm.name == category or itm.treename == category:
                    return itm.getNodeFromPath('/'+respath, metatype)
    raise TransportError('Zope transport could not be found: %s || %s'%(category, respath))

(wxID_PFE, wxID_PFT, wxID_PFL) = Utils.wxNewIds(3)

class BaseExplorerTree(wxTreeCtrl):
    def __init__(self, parent, images):
        wxTreeCtrl.__init__(self, parent, wxID_PFT, style=wxTR_HAS_BUTTONS|wxCLIP_CHILDREN)
        EVT_TREE_ITEM_EXPANDING(self, wxID_PFT, self.OnOpen)
        EVT_TREE_ITEM_EXPANDED(self, wxID_PFT, self.OnOpened)
        EVT_TREE_ITEM_COLLAPSED(self, wxID_PFT, self.OnClose)
        self.SetImageList(images)
        self.itemCache = None

        self.buildTree()

    def buildTree(self):
        pass

    def destroy(self):
        pass

    def openDefaultNodes(self):
        rootItem = self.GetRootItem()
        self.SetItemHasChildren(rootItem, true)
        self.Expand(rootItem)
        return rootItem

    def getChildren(self):
        children = []
        cookie = 0
        selection = self.GetSelection()
        child, cookie = self.GetFirstChild(selection, cookie)
        while child.IsOk():
            children.append(child)
            child, cookie = self.GetNextChild(selection, cookie)
        return children

    def getChildrenNames(self):
        return map(lambda id, tree = self: tree.GetItemText(id), self.getChildren())

    def getChildNamed(self, node, name):
        cookie = 0
        child, cookie = self.GetFirstChild(node, cookie)
        while child.IsOk() and self.GetItemText(child) != name:
            child, cookie = self.GetNextChild(node, cookie)
        return child

    def OnOpened(self, event):
        pass

    def OnOpen(self, event):
        item = event.GetItem()
        if self.IsExpanded(item): return
        data = self.GetPyData(item)
        hasFolders = true
        if data:
            wxBeginBusyCursor()
            try:
                self.DeleteChildren(item)
                if self.itemCache:
                    lst = self.itemCache[:]
                else:
                    lst = data.openList()
                hasFolders = false
                for itm in lst:
                    if itm.isFolderish():
                        hasFolders = true
                        new = self.AppendItem(item, itm.treename or itm.name,
                              itm.imgIdx, -1, wxTreeItemData(itm))
                        self.SetItemHasChildren(new, true)
                        if itm.bold:
                            self.SetItemBold(new, true)
                        if itm.refTree:
                            itm.treeitem = new
                        if itm.colour:
                            self.SetItemTextColour(new, itm.colour)
            finally:
                wxEndBusyCursor()

        self.SetItemHasChildren(item, true)#hasFolders)

    def OnClose(self, event):
        item = event.GetItem()
        data = self.GetPyData(item)
        data.closeList()

def importTransport(moduleName):
    try:
        __import__(moduleName, globals())
    except ImportError, error:
        wxLogWarning('%s not installed: %s' %(moduleName, str(error)))
        ExplorerNodes.failedModules[moduleName] = str(error)
        return true
    else:
        ExplorerNodes.installedModules.append(moduleName)
        return false

class ExplorerTree(BaseExplorerTree):
    def __init__(self, parent, images):
        BaseExplorerTree.__init__(self, parent, images)
        self._ref_all_transp = false

    def buildTree(self):
        conf = Utils.createAndReadConfig('Explorer')
        self.importExplorers(conf)

        # Create clipboards for all registered nodes
        self.clipboards = {'global': ExplorerNodes.GlobalClipper()}
        for Clss, info in ExplorerNodes.explorerNodeReg.items():
            Clip = info['clipboard']
            if type(Clip) == ClassType:
                self.clipboards[Clss.protocol] = Clip(self.clipboards['global'])

        # Root node and transports
        self.boaRoot = ExplorerNodes.RootNode('Boa Constructor')
        rootItem = self.AddRoot('', EditorHelper.imgBoaLogo, -1,
              wxTreeItemData(self.boaRoot))
        self.transports = ExplorerNodes.ContainerNode('Transport', EditorHelper.imgFolder)
        self.transports.entriesByProt = {}

        global all_transports
        if all_transports is None:
            all_transports = self.transports
            self._ref_all_transp = true

        self.transports.bold = true

        self.recentFiles = \
            ExplorerNodes.MRUCatNode(self.clipboards, conf, None,
            self.transports, self)

        self.bookmarks = ExplorerNodes.BookmarksCatNode(self.clipboards, conf,
            None, self.transports, self)

        self.sysPath = ExplorerNodes.nodeRegByProt['sys.path'](
              self.clipboards['file'], None, self.bookmarks)

        self.osCwd = ExplorerNodes.nodeRegByProt['os.cwd'](
              self.clipboards['file'], None, self.bookmarks)

        self.preferences = \
              ExplorerNodes.nodeRegByProt['boa.prefs.group'](self.boaRoot)

        assert self.clipboards.has_key('file'), 'File system transport must be loaded'

        # root level of the tree
        self.boaRoot.entries = [self.recentFiles, self.bookmarks,
            self.transports, self.sysPath, self.osCwd, self.preferences]

        # Populate transports with registered node categories
        # Protocol also has to be defined in the explorer section of the config
        transport_order = eval(conf.get('explorer', 'transportstree'))
        for name in transport_order:
            for Clss in ExplorerNodes.explorerNodeReg.keys():
                if Clss.protocol == name:
                    Cat = ExplorerNodes.explorerNodeReg[Clss]['category']
                    if not Cat: break

                    Clip = ExplorerNodes.explorerNodeReg[Clss]['clipboard']
                    if type(Clip) == type(''):
                        clip = self.clipboards[Clip]
                    elif self.clipboards.has_key(Clss.protocol):
                        clip = self.clipboards[Clss.protocol]
                    else:
                        clip = None

                    confSect, confItem = ExplorerNodes.explorerNodeReg[Clss]['confdef']
                    if conf.has_option(confSect, confItem):
                        try:
                            cat = Cat(clip, conf, None, self.bookmarks)
                            self.transports.entries.append(cat)
                            self.transports.entriesByProt[Cat.itemProtocol] = cat
                        except Exception, error:
                            wxLogWarning('Transport category %s not added: %s'\
                                   %(Cat.defName, str(error)))
                    break

    def importExplorers(self, conf):
        """ Import names defined in the config files to register them """
        installTransports = ['Explorers.PrefsExplorer'] + \
              eval(conf.get('explorer', 'installedtransports'))

        warned = false
        for moduleName in installTransports:
            warned = importTransport(moduleName)
        if warned:
            wxLogWarning('One or more transports could not be loaded, if the problem '
                         'is not rectifiable,\nconsider removing the transport under '
                         'Preferences->Plug-ins->Transports. Click "Details"')

    def destroy(self):
        if self._ref_all_transp:
            global all_transports
            all_transports = None
        self.transports = None
        self.clipboards = None
        self.defaultBookmarkItem = None
        self.bookmarks.cleanup()
        self.bookmarks = None
        self.boaRoot = None

    def openDefaultNodes(self):
        rootItem = BaseExplorerTree.openDefaultNodes(self)

        bktn = self.getChildNamed(rootItem, 'Bookmarks')
        self.Expand(bktn)

        trtn = self.getChildNamed(rootItem, 'Transport')
        self.Expand(trtn)

        self.defaultBookmarkItem = self.getChildNamed(bktn,
              self.boaRoot.entries[1].getDefault())

class BaseExplorerList(wxListCtrl, Utils.ListCtrlSelectionManagerMix):
    def __init__(self, parent, filepath, pos=wxDefaultPosition,
          size=wxDefaultSize, updateNotify=None, style=0, menuFunc=None):
        wxListCtrl.__init__(self, parent, wxID_PFL, pos=pos, size=size,
              style=wxLC_LIST | wxLC_EDIT_LABELS | wxCLIP_CHILDREN | style)
        Utils.ListCtrlSelectionManagerMix.__init__(self)

        self.filepath = filepath
        self.idxOffset = 0
        self.updateNotify = updateNotify
        self.node = None
        self.menuFunc = menuFunc

        self.selected = -1

        self.items = None
        self.currImages = None

        self._destr = false

        self.setLocalFilter()

        #Utils.ListCtrlLabelEditFixEH(self)

    def destroy(self, dont_pop=0):
        if self._destr: return

        self.DeleteAllItems()
        # XXX workaround for a crash, (better to leak than to crash ;)
        #if not dont_pop:
        #    self.PopEventHandler(true)

        if self.node:
            self.node.destroy()
        self.currImages = None
        self.items = None
        self.node = None
        self._destr = true

    def EditLabel(self, index):
        wxYield()

        try: return wxListCtrl.EditLabel(self, index)
        except AttributeError: return 0

    def getPopupMenu(self):
        return self.menuFunc()

#---Selection-------------------------------------------------------------------
    def selectItemNamed(self, name):
        for idx in range(self.GetItemCount()):
            item = self.GetItem(idx)
            if item.GetText() == name:
                item.SetState(wxLIST_STATE_FOCUSED | wxLIST_STATE_SELECTED)
                self.SetItem(item)
                self.EnsureVisible(idx)
                self.selected = idx
                return item

    def selectItemByIdx(self, idx):
        item = self.GetItem(idx)
        item.SetState(wxLIST_STATE_FOCUSED | wxLIST_STATE_SELECTED)
        self.SetItem(item)
        self.selected = idx
        return item

    def hasItemNamed(self, name):
        for idx in range(self.GetItemCount()):
            if self.GetItemText(idx) == name:
                return true
        return false

    def getAllNames(self):
        names = []
        for idx in range(self.GetItemCount()):
            name = self.GetItemText(idx)
            if name != '..':
                names.append(name)
        return names

    def getSelection(self):
        # XXX Fix, this can return IndexErrors !!!
        if self.selected >= self.idxOffset:
            return self.items[self.selected-self.idxOffset]
        else:
            return None

    def getMultiSelection(self):
        """ Returns list of indexes that map back to node list """
        res = []
        # if deselection occured, ignore item state and return []
        if self.selected == -1:
            return res
        for idx in range(self.idxOffset, self.GetItemCount()):
            if self.GetItemState(idx, wxLIST_STATE_SELECTED):
                res.append(idx-self.idxOffset)
        return res

    def setLocalFilter(self, filter='*'):
        if glob.has_magic(filter):
            self.localFilter = filter
        else:
            self.localFilter = '*'

    def refreshCurrent(self):
        self.refreshItems(self.currImages, self.node)

    def refreshItems(self, images, explNode):
        """ Display ExplorerNode items """

        # Try to get the file listing before changing anything.
        wxBeginBusyCursor()
        try: items = explNode.openList()
        finally: wxEndBusyCursor()

        self.selected = -1

        if self.node:
            self.node.destroy()

        self.node = explNode
        self.DeleteAllItems()
        self.SetImageList(images, wxIMAGE_LIST_SMALL)
        self.currImages = images

        # Build a filtered, sorted list
        orderedList = []
        for itm in items:
            name = itm.treename or itm.name
            if fnmatch.fnmatch(name, self.localFilter):
                if Preferences.exCaseInsensitiveSorting:
                    sortName = string.lower(name)
                else:
                    sortName = name
                orderedList.append( (not itm.isFolderish(), sortName, name, itm) )
        if not explNode.vetoSort :
            orderedList.sort()

        # Populate the ctrl
        self.items = []
        self.InsertImageStringItem(self.GetItemCount(), '..', explNode.upImgIdx)
        self.idxOffset = 1
        for dummy, dummy, name, itm in orderedList:
            self.items.append(itm)
            self.InsertImageStringItem(self.GetItemCount(), name, itm.imgIdx)

        self.filepath = explNode.resourcepath

        if self.updateNotify:
            self.updateNotify()

    def openNodeInEditor(self, item, editor, recentFiles):
        if self.node.parentOpensChildren:
            res = self.node.open(item, editor)
        else:
            res = item.open(editor)

        if res and len(res) == 2:
            mod, ctrlr = res

            if recentFiles and mod:
                recentFiles.add(mod.filename)

    def OnItemSelect(self, event):
        self.selected = event.m_itemIndex
        event.Skip()

    def OnItemDeselect(self, event):
        if not self.GetSelectedItemCount():
            self.selected = -1
        event.Skip()

class ExplorerList(BaseExplorerList):
    pass

class BaseExplorerSplitter(wxSplitterWindow):
    def __init__(self, parent, modimages, editor,
          XList=ExplorerList, XTree=ExplorerTree):
        wxSplitterWindow.__init__(self, parent, wxID_PFE,
              style = wxCLIP_CHILDREN | wxNO_3D | wxSP_3D)

        self.editor = editor
        self.list, self.listContainer = self.createList(XList, '')
        self.modimages = modimages

        EVT_LIST_ITEM_ACTIVATED(self.list, self.list.GetId(), self.OnOpen)

        EVT_LEFT_DOWN(self.list, self.OnListClick)

        EVT_LIST_ITEM_SELECTED(self.list, wxID_PFL, self.OnItemSelect)
        EVT_LIST_ITEM_DESELECTED(self.list, wxID_PFL, self.OnItemDeselect)

        self.tree, self.treeContainer = self.createTree(XTree, modimages)

        EVT_TREE_SEL_CHANGING(self, wxID_PFT, self.OnSelecting)
        EVT_TREE_SEL_CHANGED(self, wxID_PFT, self.OnSelect)

        self.controllers = self.initInstalledControllers()

        EVT_LIST_BEGIN_LABEL_EDIT(self, wxID_PFL, self.OnBeginLabelEdit)
        EVT_LIST_END_LABEL_EDIT(self, wxID_PFL, self.OnEndLabelEdit)

        self.SplitVertically(self.treeContainer, self.listContainer,
              Preferences.exDefaultTreeWidth)

        self.SetMinimumPaneSize(self.GetSashSize())

        self.list.SetFocus()

    def createTree(self, XTree, modimages):
        tree = XTree(self, modimages)
        return tree, tree

    def createList(self, XList, name):
        list = XList(self, name, updateNotify=self.OnUpdateNotify,
              menuFunc=self.getMenu)
        return list, list

    def addTools(self, toolbar):
        if self.list.node and self.controllers.has_key(self.list.node.protocol):
            prot = self.list.node.protocol
            tbMenus = []
            for menuLst in self.controllers[prot].toolbarMenus:
                tbMenus.extend(list(menuLst))

            for wID, name, meth, bmp in tbMenus:
                if name == '-' and not bmp:
                    toolbar.AddSeparator()
                elif bmp != '-':
                    if name[0] == '+':
                        # XXX Add toggle button
                        name = name [1:]
                    Utils.AddToolButtonBmpObject(self.editor, toolbar,
                          IS.load(bmp), name, meth)

    def getMenu(self):
        if self.list.node and self.controllers.has_key(self.list.node.protocol):
            return self.controllers[self.list.node.protocol].menu
        else:
            return None

    def destroy(self):
        if not self.editor:
            return
        self.modimages = None
        self.list.Enable(false)
        self.list.destroy()
        self.tree.Enable(false)
        self.tree.destroy()
        unqDct = {}
        for contr in self.controllers.values():
            unqDct[contr] = None
        for contr in unqDct.keys():
            contr.destroy()
        self.controllers = None
        self.list = None
        self.editor = None

    def editorUpdateNotify(self):
        if self.list.node and self.controllers.has_key(self.list.node.protocol):
            self.controllers[self.list.node.protocol].editorUpdateNotify()

    def selectTreeItem(self, item):
        data = self.tree.GetPyData(item)
        title = self.tree.GetItemText(item)
        if data:
            imgs = data.images
            if not imgs: imgs = self.modimages
            self.list.refreshItems(imgs, data)
            title = data.getTitle()

        self.editor.SetTitle('Editor - Explorer - %s' % title)

#---Create Controllers----------------------------------------------------------
    def initInstalledControllers(self):
        """ Creates controllers for built-in, plugged-in and installed nodes
            in the order specified by installedModules """
        controllers = {}

        return controllers

    def OnUpdateNotify(self):
        tItm = self.tree.GetSelection()
        # XXX this should be smarter, only refresh on folderish name change
        # XXX add or remove
        if not self.selecting and self.tree.IsExpanded(tItm):
            self.tree.Collapse(tItm)
            self.tree.Expand(tItm)

        # XXX this is ugly :(
        # only update toolbar when the explorer is active
        if self.editor.tabs.GetSelection() == 1:
            self.editor.setupToolBar(1)

    def OnSelecting(self, event):
        self.selecting = true

    def OnSelect(self, event):
        # Event is triggered twice, work around with flag
        if self.selecting:
            item = event.GetItem()
            self.selectTreeItem(item)
        self.selecting = false

        event.Skip()

    def OnOpen(self, event):
        tree, list = self.tree, self.list
        if list.selected != -1:
            name = list.GetItemText(self.list.selected)
            nd = list.node
            if name == '..':
                if not nd.openParent(self.editor):
                    treeItem = tree.GetItemParent(tree.GetSelection())
                    if treeItem.IsOk():
                        tree.SelectItem(treeItem)
            else:
##                if event and event.AltDown() and \
##                      self.controllers.has_key(list.node.protocol):
##                    ctrlr = self.controllers[list.node.protocol]
##                    if hasattr(ctrlr, 'OnInspectItem'):
##                        event.Skip()
##                        ctrlr.OnInspectItem(None)
##                        return
                item = list.items[list.selected-1]
                if item.isFolderish():
                    tItm = tree.GetSelection()
                    if not tree.IsExpanded(tItm):
                        tree.itemCache = self.list.items
                        try: tree.Expand(tItm)
                        finally: tree.itemCache = None
                    chid = tree.getChildNamed(tree.GetSelection(), name)
                    tree.SelectItem(chid)
                else:
                    list.openNodeInEditor(item, self.editor, tree.recentFiles)

    def OnKeyPressed(self, event):
        key = event.KeyCode()
        if key == 13:
            self.OnOpen(event)
        else:
            event.Skip()

    def OnListClick(self, event):
        palette = self.editor.palette

        if palette.componentSB.selection and self.list.node and \
              self.list.node.canAdd(palette.componentSB.prevPage.name):
            name, desc, Compn = palette.componentSB.selection
            newName = self.list.node.newItem(name, Compn)
            try:
                self.list.refreshCurrent()
                self.list.selectItemNamed(newName)
            finally:
                palette.componentSB.selectNone()
        else:
            event.Skip()

    def OnBeginLabelEdit(self, event):
        self.oldLabelVal = event.GetText()
        if self.list.node:
            self.list.node.notifyBeginLabelEdit(event)

        if event.IsAllowed():
            event.Skip()

    def OnEndLabelEdit(self, event):
        newText = event.GetText()
        renameNode = self.list.getSelection()
        assert renameNode, 'There must be a selection to rename'
        oldURI = renameNode.getURI()
        if newText != self.oldLabelVal:
            event.Skip()
            self.list.node.renameItem(self.oldLabelVal, newText)
            self.list.refreshCurrent()
            # XXX Renames on files with unsaved changes should have opt out
            # XXX Maybe load renamedNode from openEx
            self.list.selectItemNamed(newText)
            renamedNode = self.list.getSelection()
            # XXX Type changes and unknown types are not handled!
            if renamedNode:
                self.editor.explorerRenameNotify(oldURI, renamedNode)
        else:
            event.Skip()

    def OnItemSelect(self, event):
        self.list.OnItemSelect(event)
        if self.list.node:
            sel = self.list.getSelection()
            if not sel: sel = self.list.node
            self.editor.statusBar.setHint(sel.getDescription())

    def OnItemDeselect(self, event):
        self.list.OnItemDeselect(event)
        if self.list.node:
            self.editor.statusBar.setHint(self.list.node.getDescription())

    def OnSplitterDoubleClick(self, event):
        pass

class ExplorerSplitter(BaseExplorerSplitter):
    def initInstalledControllers(self):
        """ Creates controllers for built-in, plugged-in and installed nodes
            in the order specified by installedModules """
        controllers = {}
        links = []
        for instMod in ['Explorers.ExplorerNodes', 'PaletteMapping'] +\
                       ExplorerNodes.installedModules:
            for Clss, info in ExplorerNodes.explorerNodeReg.items():
                if Clss.__module__ == instMod and info['controller']:
                    Ctrlr = info['controller']
                    if type(Ctrlr) == type(''):
                        links.append((Clss.protocol, Ctrlr))
                    else:
                        controllers[Clss.protocol] = Ctrlr(self.editor,
                          self.list, self.editor.inspector, controllers)
        for protocol, link in links:
            controllers[protocol] = controllers[link]

        return controllers

