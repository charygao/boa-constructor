#----------------------------------------------------------------------
# Name:        relpath.py
# Purpose:
#
# Author:      Riaan Booysen
#
# Created:     1999
# RCS-ID:      $Id$
# Copyright:   (c) 1999, 2000 Riaan Booysen
# Licence:     GPL
#----------------------------------------------------------------------

##b = 'c:\\a\\b\\f\\d'
##d = 'c:\\a\\b\\f\\h.txt'
##d = 'c:\\a\\b\\h\\i\\j.txt'
##e = 'd:\\z\\x\\y\\j\\k.txt'

import os, string
from os import path

def splitpath(apath):
    """ Splits a path into a list of directory names """
    path_list = []
    drive, apath = path.splitdrive(apath)
    head, tail = path.split(apath)
    while 1:
        if tail:
            path_list.insert(0, tail)
        newhead, tail = path.split(head)
        if newhead == head:
            break
        else:
            head = newhead
    if drive:
        path_list.insert(0, drive)
    return path_list


def relpath(base, comp):
    """ Return a path to file comp relative to path base. """
    protsplitbase = string.split(base, '://')
    if len(protsplitbase) == 1:
        baseprot, nbase = 'file', protsplitbase[0]
    elif len(protsplitbase) == 2:
        baseprot, nbase = protsplitbase
    elif len(protsplitbase) == 3:
        baseprot, nbase, zipentry = protsplitbase
    else:
        raise 'Unhandled path %s'%`protsplitbase`

    protsplitcomp = string.split(comp, '://')
    if len(protsplitcomp) == 1:
        compprot, ncomp  = 'file', protsplitcomp[0]
    elif len(protsplitcomp) == 2:
        compprot, ncomp = protsplitcomp
    elif len(protsplitcomp) == 3:
        compprot, ncomp, zipentry = protsplitcomp
    else:
        raise 'Unhandled path %s'%`protsplitcomp`

    if baseprot != compprot:
        return comp
        
    base_drive, base_path = path.splitdrive(nbase)
    comp_drive, comp_path = path.splitdrive(ncomp)
    base_path_list = splitpath(base_path)
    comp_path_list = splitpath(comp_path)

    if base_drive != comp_drive:
        return comp

    # relative path defaults to the list of files with
    # a greater index then the entire base
    rel_path = comp_path_list[len(base_path_list):]
    # find the first directory for which the 2 paths differ
    found = -1
    for idx in range(len(base_path_list)):
        if base_path_list[idx] != comp_path_list[idx]:
            rel_path = comp_path_list[idx:]
            found = 0
            break
    for cnt in range(max(len(base_path_list) - idx + found, 0)):
        rel_path.insert(0, os.pardir)

    return apply(path.join, rel_path)

#print relpath(b, d)