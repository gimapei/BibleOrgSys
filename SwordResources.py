#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SwordResources.py
#
# Interface module handling Sword resources
#   using either the Sword engine (if available) or else our own software
#
# Copyright (C) 2013-2016 Robert Hunt
# Author: Robert Hunt <Freely.Given.org@gmail.com>
# License: See gpl-3.0.txt
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
This is the interface module used to give a unified interface to either:
    1/ The Crosswire Sword engine (libsword) via Python3 SWIG bindings,
        or, if that's not available, to
    2/ Our own SwordInstallManager.py which downloads modules from remote
        repositories, and our (still primitive) module that reads Sword
        files directly called SwordModules.py
"""

from gettext import gettext as _

LastModifiedDate = '2016-05-03' # by RJH
ShortProgName = "SwordResources"
ProgName = "Sword resource handler"
ProgVersion = '0.22'
ProgNameVersion = '{} v{}'.format( ShortProgName, ProgVersion )
ProgNameVersionDate = '{} {} {}'.format( ProgNameVersion, _("last modified"), LastModifiedDate )

debuggingThisModule = False


#from singleton import singleton
import logging, re


import BibleOrgSysGlobals
from VerseReferences import SimpleVerseKey
from InternalBibleInternals import InternalBibleEntryList, InternalBibleEntry


SwordType = None
try:
    import Sword # Python bindings for the Crosswire Sword C++ library
    SwordType = 'CrosswireLibrary'
    SWORD_TEXT_DIRECTIONS = { Sword.DIRECTION_LTR:'LTR', Sword.DIRECTION_RTL:'RTL', Sword.DIRECTION_BIDI:'BiDi' }
    SWORD_MARKUPS = { Sword.FMT_UNKNOWN:'Unknown', Sword.FMT_PLAIN:'Plain', Sword.FMT_THML:'THML',
                     Sword.FMT_GBF:'GBF', Sword.FMT_HTML:'HTML', Sword.FMT_HTMLHREF:'HTMLHREF',
                     Sword.FMT_RTF:'RTF', Sword.FMT_OSIS:'OSIS', Sword.FMT_WEBIF:'WEBIF',
                     Sword.FMT_TEI:'TEI', Sword.FMT_XHTML:'XHTML' }
    try: SWORD_MARKUPS[Sword.FMT_LATEX] = 'LaTeX'
    except AttributeError: pass # Sword 1.7.4 doesn't have this
    SWORD_ENCODINGS = { Sword.ENC_UNKNOWN:'Unknown', Sword.ENC_LATIN1:'Latin1',
                    Sword.ENC_UTF8:'UTF8', Sword.ENC_SCSU:'SCSU', Sword.ENC_UTF16:'UTF16',
                    Sword.ENC_RTF:'RTF', Sword.ENC_HTML:'HTML' }
except ImportError: # Sword library (dll and python bindings) seem to be not available
    try:
        import SwordModules # Not as good/reliable/efficient as the real Sword library, but better than nothing
        SwordType = 'OurCode'
    except ImportError:
        logging.critical( _("You don't appear to have any way installed to read Sword modules.") )



def exp( messageString ):
    """
    Expands the message string in debug mode.
    Prepends the module name to a error or warning message string
        if we are in debug mode.
    Returns the new string.
    """
    try: nameBit, errorBit = messageString.split( ': ', 1 )
    except ValueError: nameBit, errorBit = '', messageString
    if BibleOrgSysGlobals.debugFlag or debuggingThisModule:
        nameBit = '{}{}{}'.format( ShortProgName, '.' if nameBit else '', nameBit )
    return '{}{}'.format( nameBit+': ' if nameBit else '', errorBit )
# end of exp



def replaceFixedPairs( replacementList, verseLine ):
    """
    Given a set of 4-tuples, e.g., ('<divineName>','\\nd ','</divineName>','\\nd*')
        search for matching opening and closing pairs and make the replacements,
        issuing errors for mismatches.

    Since we've handling verse segments, it's possible that
        the opening segment was in the previous verse
        or the closing segment is in the next verse.
    In that case, place missing opening segments right at the beginning of the verse
        and missing closing segments right at the end.

    Returns the new verseLine.
    """
    for openCode,newOpenCode,closeCode,newCloseCode in replacementList:
        ix = verseLine.find( openCode )
        while ix != -1:
            #print( '{} {!r}->{!r} {!r}->{!r} in {!r}'.format( ix, openCode,newOpenCode,closeCode,newCloseCode, verseLine ) )
            verseLine = verseLine.replace( openCode, newOpenCode, 1 )
            ixEnd = verseLine.find( closeCode, ix )
            if ixEnd == -1:
                logging.error( 'Missing {!r} close code to match {!r}'.format( closeCode, openCode ) )
                verseLine = verseLine + newCloseCode # Try to fix it by adding a closing code at the end
            else:
                verseLine = verseLine.replace( closeCode, newCloseCode, 1 )
            ix = verseLine.find( openCode, ix )
        if verseLine.find( closeCode ) != -1:
            logging.error( 'Unexpected {!r} close code without any previous {!r}'.format( closeCode, openCode )  )
            verseLine = verseLine.replace( closeCode, newCloseCode, 1 )
            # Try to fix it by adding an opening code at or near the beginning of the line
            #   but we have to skip past any paragraph markers
            insertIndex = 0
            while verseLine[insertIndex] == '\\':
                insertIndex += 1
                while insertIndex < len(verseLine)-1:
                    if verseLine[insertIndex] == ' ': break
                    insertIndex += 1
            if insertIndex != 0 and debuggingThisModule: print( "insertIndex={} vL={!r}".format( insertIndex, verseLine ) )
            verseLine = verseLine[:insertIndex] + ' '+newOpenCode + verseLine[insertIndex:]
            if insertIndex != 0 and debuggingThisModule: print( "new vL={!r}".format( verseLine ) )

    return verseLine
# end of replaceFixedPairs



def filterOSISVerseLine( osisVerseString, moduleName, BBB, C, V ):
    """
    Given a verse entry string made up of OSIS segments,
        convert it into our internal format

    moduleName, BBB, C, V are just used for more helpful error/information messages.

    OSIS is a pig to extract the information out of,
        but we use it nevertheless because it's the native format
        and hence most likely to represent the original well.

    We use \\NL** as an internal code for a newline
        to show where a verse line needs to be broken into internal chunks.

    Returns the filtered line(s).
    """
    if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
        print( "\nfilterOSISVerseLine( {} {} {}:{} … {!r} )".format( moduleName, BBB, C, V, osisVerseString ) )

    verseLine = osisVerseString


    def handleOSISWordAttributes( attributeString ):
        """
        Handle OSIS XML attributes from the <w …> field.

        Returns the string to replace the attributes.
        """
        attributeReplacementResult = ''
        attributeCount = attributeString.count( '="' )
        #print( 'Attributes={} {!r}'.format( attributeCount, attributeString ) )
        for j in range( 0, attributeCount ):
            match2 = re.search( 'savlm="(.+?)"', attributeString )
            if match2:
                savlm = match2.group(1)
                #print( 'savlm', repr(savlm) )
                while True:
                    match3 = re.search( 'strong:([GH]\d{1,5})', savlm )
                    if not match3: break
                    #print( 'string', repr(match3.group(1) ) )
                    attributeReplacementResult += '\\str {}\\str*'.format( match3.group(1) )
                    savlm = savlm[:match3.start()] + savlm[match3.end():] # Remove this Strongs' number
                attributeString = attributeString[:match2.start()] + attributeString[match2.end():] # Remove this attribute entry

            match2 = re.search( 'lemma="(.+?)"', attributeString )
            if match2:
                lemma = match2.group(1)
                #print( 'lemma', repr(lemma) )
                while True:
                    match3 = re.search( 'strong:([GH]\d{1,5})', lemma )
                    if not match3: break
                    #print( 'string', repr(match3.group(1) ) )
                    attributeReplacementResult += '\\str {}\\str*'.format( match3.group(1) )
                    lemma = lemma[:match3.start()] + lemma[match3.end():] # Remove this Strongs' number
                attributeString = attributeString[:match2.start()] + attributeString[match2.end():] # Remove this attribute entry

            match2 = re.search( 'morph="(.+?)"', attributeString )
            if match2:
                morph = match2.group(1)
                #print( 'morph', repr(morph) )
                while True:
                    match3 = re.search( 'strongMorph:(TH\d{1,4})', morph )
                    if not match3: break
                    #print( 'string', repr(match3.group(1) ) )
                    attributeReplacementResult += '\\morph {}\\morph*'.format( match3.group(1) )
                    morph = morph[:match3.start()] + morph[match3.end():] # Remove this Strongs' number
                attributeString = attributeString[:match2.start()] + attributeString[match2.end():] # Remove this attribute entry

            match2 = re.search( 'type="(.+?)"', attributeString )
            if match2:
                typeValue = match2.group(1)
                #print( 'typeValue', repr(typeValue) ) # Seems to have an incrementing value on the end for some reason
                assert typeValue.startswith( 'x-split' ) # e.g., x-split or x-split-1 -- what do these mean?
                attributeString = attributeString[:match2.start()] + attributeString[match2.end():] # Remove this attribute entry
            match2 = re.search( 'subType="(.+?)"', attributeString )
            if match2:
                subType = match2.group(1)
                #print( 'subType', repr(subType) ) # e.g., x-28 -- what does this mean?
                attributeString = attributeString[:match2.start()] + attributeString[match2.end():] # Remove this attribute entry

            match2 = re.search( 'src="(.+?)"', attributeString ) # Can be two numbers separated by a space!
            if match2:
                src = match2.group(1)
                #print( 'src', repr(src) ) # What does this mean?
                attributeString = attributeString[:match2.start()] + attributeString[match2.end():] # Remove this attribute entry

            match2 = re.search( 'wn="(\d+?)"', attributeString )
            if match2:
                wn = match2.group(1)
                #print( 'wn', repr(wn) ) # What does this mean?
                attributeString = attributeString[:match2.start()] + attributeString[match2.end():] # Remove this attribute entry

        if attributeString.strip():
            print( 'Unhandled word attributes', repr(attributeString) )
            if BibleOrgSysGlobals.debugFlag: halt
        #print( 'attributeReplacementResult', repr(attributeReplacementResult) )
        return attributeReplacementResult
    # end of handleOSISWordAttributes


    # Start of main code for filterOSISVerseLine
    # Straight substitutions
    for old, new in ( ( ' />', '/>' ),
                      ( '<milestone marker="¶" type="x-p"/>', '\\NL**\\p\\NL**' ),
                      ( '<milestone marker="¶" subType="x-added" type="x-p"/>', '\\NL**\\p\\NL**' ),
                      ( '<milestone type="x-extra-p"/>', '\\NL**\\p\\NL**' ),
                      ( '<milestone type="line"/><milestone type="line"/>', '\\NL**\\b\\NL**' ),
                      ( '<milestone type="line"/>', '\\NL**' ),
                      ( '<titlePage>', '\\NL**' ), ( '</titlePage>', '\\NL**' ),
                      ( '<lb type="x-begin-paragraph"/>', '\\NL**\\p\\NL**' ), # in ESV
                      ( '<lb type="x-end-paragraph"/>', '\\NL**' ), # in ESV
                      ( '<lb subType="x-same-paragraph" type="x-begin-paragraph"/>', '\\NL**' ), # in ESV
                      ( '<lb subType="x-extra-space" type="x-begin-paragraph"/>', '\\NL**\\b\\NL**' ), # in ESV
                      ( '<lb/>', '\\NL**' ),
                      ( '<lb type="x-unparagraphed"/>', '' ),
                      ( '<list>', '\\NL**' ), ( '</list>', '\\NL**' ),
                      ( '<l/>', '\\NL**\\q1\\NL**' ),
                      ( '<title subtype="x-preverse" type="section"></title>', '' ), # NetFree why???
                      ):
        verseLine = verseLine.replace( old, new )

    # Delete info line(s)
    match = re.search( '<milestone type="x-importer" subType="x-osis2mod" n="\\$Rev: .+? \\$"/>', verseLine )
    if match:
        verseLine = verseLine[:match.start()] + verseLine[match.end():] # Delete it

    # Delete end book and chapter (self-closing) markers (we'll add our own later)
    while True: # Delete end book markers (should only be maximum of one theoretically but not always so)
        match = re.search( '<div [^/>]*?eID=[^/>]+?/>', verseLine )
        if not match: break
        verseLine = verseLine[:match.start()] + verseLine[match.end():]
    while True: # Delete preverse milestones
        match = re.search( '<div [^/>]*?subType="x-preverse"[^/>]*?/>', verseLine )
        if not match: break
        verseLine = verseLine[:match.start()] + verseLine[match.end():]
    while True:
        match = re.search( '<div [^/>]*?type="front"[^/>]*?/>', verseLine )
        if not match: break
        assert V == '0'
        verseLine = verseLine[:match.start()] + verseLine[match.end():] # It's in v0 anyway so no problem
    while True:
        match = re.search( '<div ([^/>]*?)type="section"([^/>]*?)>', verseLine )
        if not match: break
        attributes = match.group(1) + match.group(2)
        #print( "Div section attributes={!r}".format( attributes ) )
        assert 'scope="' in attributes
        verseLine = verseLine[:match.start()] + verseLine[match.end():]
    while True:
        match = re.search( '<div [^/>]*?type="colophon"[^/>]*?/>', verseLine )
        if not match: break
        verseLine = verseLine[:match.start()] + verseLine[match.end():] # Not sure what this is (Rom 16:27) but delete it for now
    while True: # Delete end chapter markers (should only be maximum of one theoretically)
        match = re.search( '<chapter [^/>]*?eID=[^/>]+?/>', verseLine )
        if not match: break
        verseLine = verseLine[:match.start()] + verseLine[match.end():]
    while True: # Delete start verse markers (should only be maximum of one theoretically but can be more -- bridged verses???)
        match = re.search( '<verse [^/>]*?osisID="[^/>]+?"[^/>]*?>', verseLine )
        if not match: break
        assert V != '0'
        verseLine = verseLine[:match.start()] + verseLine[match.end():]
    verseLine = verseLine.replace( '</verse>', '' ) # Delete left-overs (normally expected at the end of the verse line)
    while True: # Delete lg start and end milestones
        match = re.search( '<lg [^/>]+?/>', verseLine )
        if not match: break
        verseLine = verseLine[:match.start()] + verseLine[match.end():]

    # Other regular expression data extractions
    match = re.search( '<chapter ([^/>]*?)sID="([^/>]+?)"([^/>]*?)/>', verseLine )
    if match:
        attributes, sID = match.group(1) + match.group(3), match.group(2)
        #print( 'Chapter sID {!r} attributes={!r} @ {} {}:{}'.format( sID, attributes, BBB, C, V ) )
        assert C and C != '0'
        assert V == '0'
        #if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( "CCCC {!r}(:{!r})".format( C, V ) )
        verseLine = verseLine[:match.start()] + verseLine[match.end():]
    match = re.search( '<chapter ([^/>]*?)osisID="([^/>]+?)"([^/>]*?)>', verseLine )
    if match:
        attributes, osisID = match.group(1) + match.group(3), match.group(2)
        #print( 'Chapter osisID {!r} attributes={!r} @ {} {}:{}'.format( osisID, attributes, BBB, C, V ) )
        #assert C and C != '0'
        assert V == '0'
        #if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( "CCCC {!r}(:{!r})".format( C, V ) )
        verseLine = verseLine[:match.start()] + verseLine[match.end():]
    verseLine = verseLine.replace( '</chapter>', '' )
    while True:
        match = re.search( '<div ([^/>]*?)type="([^/>]+?)"([^/>]*?)/?> ?<title>(.+?)</title>', verseLine )
        if not match: break
        attributes, sectionType, words = match.group(1) + match.group(3), match.group(2), match.group(4)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Div title {!r} attributes={!r} Words={!r}'.format( sectionType, attributes, words ) )
        if sectionType == 'section': titleMarker = 's1'
        elif sectionType == 'subSection': titleMarker = 's2'
        elif sectionType == 'x-subSubSection': titleMarker = 's3'
        elif sectionType == 'majorSection': titleMarker = 'sr'
        elif sectionType == 'book': titleMarker = 'mt1'
        elif sectionType == 'introduction': titleMarker = 'iot'
        else: print( 'Matched:', repr(match.group(0)) ); halt
        replacement = '\\NL**\\{} {}\\NL**'.format( titleMarker, words )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    match = re.search( '<div ([^/>]*?)type="([^/>]+?)"([^/>]*?)/><title>', verseLine )
    if match: # handle left over div/title start fields
        attributes, sectionType = match.group(1) + match.group(3), match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Section title start {!r} attributes={!r}'.format( sectionType, attributes ) )
        if sectionType == 'section': titleMarker = 's1'
        elif sectionType == 'subSection': titleMarker = 's2'
        elif sectionType == 'x-subSubSection': titleMarker = 's3'
        else: print( 'Matched:', repr(match.group(0)) ); halt
        replacement = '\\NL**\\{} '.format( titleMarker )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<div ([^/>]*?)type="([^/>]+?)"([^/>]*?)/>.NL..<head>(.+?)</head>', verseLine )
        if not match: break
        attributes, sectionType, words = match.group(1) + match.group(3), match.group(2), match.group(4)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Section title {!r} attributes={!r} Words={!r}'.format( sectionType, attributes, words ) )
        if sectionType == 'outline': titleMarker = 'iot'
        else: print( 'Matched:', repr(match.group(0)) ); halt
        replacement = '\\NL**\\{} {}\\NL**'.format( titleMarker, words )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<div ([^/>]*?)type="([^/>]+?)"([^/>]*?)/?>', verseLine )
        if not match: break
        attributes, divType = match.group(1) + match.group(3), match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Div type={!r} attributes={!r}'.format( divType, attributes ) )
        if divType == 'x-p': replacement = '\\NL**\\p\\NL**'
        elif divType == 'glossary': replacement = '\\NL**\\id GLO\\NL**' #### WEIRD -- appended to 3 John
        elif divType == 'book': replacement = '' # We don't need this
        elif divType == 'outline': replacement = '\\NL**\\iot '
        elif divType == 'paragraph': replacement = '\\NL**\\ip ' if C=='0' else '\\NL**\\p\\NL**'
        elif divType == 'majorSection': replacement = '\\NL**\\ms\\NL**'
        elif divType == 'section': replacement = '\\NL**\\s1 '
        elif divType in ( 'preface', 'titlePage', 'introduction', ): replacement = '\\NL**\\ip '
        elif divType in ( 'x-license', 'x-trademark', ): replacement = '\\NL**\\rem '
        else: print( 'Matched:', repr(match.group(0)) ); halt
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    verseLine = verseLine.replace( '</div>', '' )
    while True:
        match = re.search( '<title type="parallel"><reference type="parallel">(.+?)</reference></title>', verseLine )
        if not match: break
        reference = match.group(1)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Parallel reference={!r}'.format( reference ) )
        replacement = '\\NL**\\r {}\\NL**'.format( reference )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<title type="scope"><reference>(.+?)</reference></title>', verseLine )
        if not match: break
        reference = match.group(1)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Section Parallel reference={!r}'.format( reference ) )
        replacement = '\\NL**\\sr {}\\NL**'.format( reference )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<title ([^/>]+?)>(.+?)</title>', verseLine )
        if not match: break
        attributes, words = match.group(1), match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Title attributes={!r} Words={!r}'.format( attributes, words ) )
        titleMarker = 's1'
        replacement = '\\NL**\\{} {}\\NL**'.format( titleMarker, words )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    verseLine = verseLine.replace( '</title>', '\\NL**' )
    verseLine = verseLine.replace( '<title>', '\\NL**\\s1 ' )
    while True:
        match = re.search( '<w ([^/>]+?)/>', verseLine )
        if not match: break
        replacement = handleOSISWordAttributes( match.group(1) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineB", repr(verseLine) )
    while True:
        match = re.search( '<w ([^/>]+?)>(.*?)</w>', verseLine ) # Can have no words inside
        if not match: break
        attributes, words = match.group(1), match.group(2)
        #print( 'AttributesC={!r} Words={!r}'.format( attributes, words ) )
        replacement = words
        replacement += handleOSISWordAttributes( attributes )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "\nverseLineW", repr(verseLine) )
    while True:
        match = re.search( '<q ([^/>]+?)>(.+?)</q>', verseLine )
        if not match: break
        attributes, words = match.group(1), match.group(2)
        if 'who="Jesus"' in attributes:
            if 'marker="' in attributes and 'marker=""' not in attributes:
                #print( 'AttributesQM={!r} Words={!r}'.format( attributes, words ) )
                if BibleOrgSysGlobals.debugFlag: halt
            replacement = '\\wj {}\\wj*'.format( words )
        else:
            #print( 'AttributesQ={!r} Words={!r}'.format( attributes, words ) )
            if BibleOrgSysGlobals.debugFlag: halt
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<q ([^/>]+?)>', verseLine ) # Leftovers (no </q>)
        if not match: break
        attributes = match.group(1)
        if 'who="Jesus"' in attributes:
            if 'marker="' in attributes and 'marker=""' not in attributes:
                #print( 'AttributesQM={!r} Words={!r}'.format( attributes, words ) )
                if BibleOrgSysGlobals.debugFlag: halt
            replacement = '\\wj '
        else:
            #print( 'AttributesQ={!r} Words={!r}'.format( attributes, words ) )
            if BibleOrgSysGlobals.debugFlag: halt
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<q ([^/>]*?)sID="(.+?)"(.*?)/>', verseLine )
        if not match: break
        attributes, sID = match.group(1) + match.group(3), match.group(2)
        #print( 'Q attributesC={!r} sID={!r}'.format( attributes, sID ) )
        match2 = re.search( 'level="(.+?)"', attributes )
        level = match2.group(1) if match2 else '1'
        match2 = re.search( 'marker="(.+?)"', attributes )
        quoteSign = match2.group(1) if match2 else ''
        replacement = '\\NL**\\q{} {}'.format( level, quoteSign )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<q ([^/>]*?)eID="(.+?)"(.*?)/>', verseLine )
        if not match: break
        attributes, eID = match.group(1) + match.group(3), match.group(2)
        #print( 'Q attributesC={!r} eID={!r}'.format( attributes, eID ) )
        match2 = re.search( 'marker="(.+?)"', attributes )
        quoteSign = match2.group(1) if match2 else ''
        replacement = '{}\\NL**'.format( quoteSign )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<q ([^/>]*?)type="block"(.*?)/>', verseLine )
        if not match: break
        attributes = match.group(1) + match.group(2)
        replacement = '\\NL**\\pc '
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<q(.*?)>(.+?)</q>', verseLine )
        if not match: break
        attributes, words = match.group(1), match.group(2)
        replacement = '\\NL**\\pc {}\\NL**'.format( words )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<l ([^/>]*?)level="(.+?)"([^/>]*?)/>', verseLine )
        if not match: break
        attributes, level = match.group(1)+match.group(3), match.group(2)
        #if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            #print( 'AttributesL={!r} Level={!r}'.format( attributes, level ) )
        assert level in '1234'
        if 'sID="' in attributes:
            replacement = '\\NL**\\q{} '.format( level )
        elif 'eID="' in attributes:
            replacement = '' # Remove eIDs completely
        else:
            print( 'Level attributesLl2={!r} Level={!r}'.format( attributes, level ) )
            halt
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<l ([^/>]+?)/>', verseLine )
        if not match: break
        attributes = match.group(1)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Level Attributes={!r}'.format( attributes ) )
        if 'sID="' in attributes:
            replacement = '\\NL**\\q1 '
        elif 'eID="' in attributes:
            replacement = '\\NL**' # Remove eIDs completely
        else:
            print( 'AttributesL2={!r} Level={!r}'.format( attributes, level ) )
            halt
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True: # handle list items
        match = re.search( '<item ([^/>]*?)type="(.+?)"([^/>]*?)>(.+?)</item>', verseLine )
        if not match: break
        attributes, itemType, item = match.group(1)+match.group(3), match.group(2), match.group(4)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Item={!r} Type={!r} attributes={!r}'.format( item, itemType, attributes ) )
        assert itemType in ( 'x-indent-1', 'x-indent-2', )
        marker = 'io' if 'x-introduction' in attributes else 'li'
        replacement = '\\NL**\\{} {}\\NL**'.format( marker+itemType[-1], item )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    match = re.search( '<item ([^/>]*?)type="(.+?)"([^/>]*?)>', verseLine )
    if match: # Handle left-over list items
        attributes, itemType = match.group(1)+match.group(3), match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Item Type={!r} attributes={!r}'.format( itemType, attributes ) )
        assert itemType in ( 'x-indent-1', 'x-indent-2', )
        marker = 'io' if 'x-introduction' in attributes else 'li'
        replacement = '\\NL**\\{}\\NL**'.format( marker+itemType[-1] )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    verseLine = verseLine.replace( '</item>', '\\NL**' )
    while True: # handle names
        match = re.search( '<name ([^/>]*?)type="(.+?)"([^/>]*?)>(.+?)</name>', verseLine )
        if not match: break
        attributes, nameType, name = match.group(1)+match.group(3), match.group(2), match.group(4)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Name={!r} Type={!r} attributes={!r}'.format( name, nameType, attributes ) )
        if nameType == 'x-workTitle': marker = 'bk'
        else: halt
        replacement = '\\{} {}\\{}*'.format( marker, name, marker )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<seg ([^/>]+?)>([^<]+?)</seg>', verseLine )
        if not match: break
        attributes, words = match.group(1), match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( 'Seg attributes={!r} Words={!r}'.format( attributes, words ) )
        if 'type="keyword"' in attributes: replacement = '\\k {}\\k*'.format( words)
        elif 'type="verseNumber"' in attributes: replacement = '\\vp {}\\NL**'.format( words)
        elif 'type="x-us-time"' in attributes: replacement = '{}'.format( words)
        elif 'type="x-transChange"' in attributes and 'subType="x-added"' in attributes: replacement = '\\add {}\\add*'.format( words)
        else: halt
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )
    while True:
        match = re.search( '<foreign ([^/>]+?)>(.+?)</foreign>', verseLine )
        if not match: break
        attributes, words = match.group(1), match.group(2)
        #print( 'Attributes={!r} Words={!r}'.format( attributes, words ) )
        replacement = '\\tl {}\\tl*'.format( words )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )
    while True:
        match = re.search( '<reference([^/>]*?)>(.+?)</reference>', verseLine )
        if not match: break
        attributes, referenceField = match.group(1), match.group(2)
        #if attributes: print( 'Attributes={!r} referenceField={!r}'.format( attributes, referenceField ) )
        marker = 'ior' if V=='0' else 'x'
        replacement = '\\{} {}\\{}*'.format( marker, referenceField, marker )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )
    while True:
        match = re.search( '<reference([^/>]*?)/>', verseLine )
        if not match: break
        attributes = match.group(1)
        #print( 'Attributes={!r}'.format( attributes ) )
        matcha = re.search( 'osisRef="(.+?)"', attributes )
        osisRef = matcha.group(1) if matcha else ''
        #print( 'osisRef={!r}'.format( osisRef ) )
        replacement = '\\x {}\\x*'.format( osisRef )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )
    while True:
        match = re.search( '<hi ([^/>]+?)>(.+?)</hi>', verseLine )
        if not match: break
        attributes, words = match.group(1), match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Highlight attributes={!r} Words={!r}'.format( attributes, words ) )
        if '"italic"' in attributes: marker = 'it'
        elif '"small-caps"' in attributes: marker = 'sc'
        elif '"super"' in attributes: marker = 'ord' # We don't have anything exact for this XXXXXXXXXXXXXXXX
        elif '"acrostic"' in attributes: marker = 'tl'
        elif '"bold"' in attributes: marker = 'bd'
        elif '"underline"' in attributes: marker = 'em' # We don't have an underline marker
        elif '"x-superscript"' in attributes: marker = 'ord' # We don't have a superscript marker
        elif BibleOrgSysGlobals.debugFlag and debuggingThisModule: halt
        replacement = '\\{} {}\\{}*'.format( marker, words, marker )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )
    while True: # Handle left-over highlights (that have no further information)
        match = re.search( '<hi>(.+?)</hi>', verseLine )
        if not match: break
        words = match.group(1)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Highlight Words={!r}'.format( words ) )
        #if moduleName in ( 'LITV', 'MKJV', 'TS1998', ):
        marker = 'add'
        replacement = '\\{} {}\\{}*'.format( marker, words, marker )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )

    # Milestones
    while True:
        match = re.search( '<milestone ([^/>]*?)type="x-usfm-(.+?)"([^/>]*?)/>', verseLine )
        if not match: break
        attributes, marker = match.group(1)+match.group(3), match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Milestone attributes={!r} marker={!r}'.format( attributes, marker ) )
        match2 = re.search( 'n="(.+?)"', attributes )
        if match2:
            replacement = '\\NL**\\{} {}\\NL**'.format( marker, match2.group(1) )
            #print( 'replacement', repr(replacement) )
        else: replacement = ''; halt
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )
    while True: # Not sure what this is all about -- just delete it
        match = re.search( '<milestone ([^/>]*?)type="x-strongsMarkup"([^/>]*?)/>', verseLine )
        if not match: break
        attributes = match.group(1)+match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Strongs milestone attributes={!r}'.format( attributes ) )
        verseLine = verseLine[:match.start()] + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )
    while True:
        match = re.search( '<milestone ([^/>]*?)type="x-p"([^/>]*?)/>', verseLine )
        if not match: break
        attributes = match.group(1)+match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'x-p milestone attributes={!r}'.format( attributes ) )
        match2 = re.search( 'marker="(.+?)"', attributes )
        if match2:
            replacement = '\\p {}\\NL**'.format( match2.group(1) )
            #print( 'replacement', repr(replacement) )
        else: replacement = ''; halt
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
        #print( "verseLineC", repr(verseLine) )
    while True:
        match = re.search( '<milestone ([^/>]*?)type="cQuote"([^/>]*?)/>', verseLine )
        if not match: break
        attributes = match.group(1)+match.group(2)
        match2 = re.search( 'marker="(.+?)"', attributes )
        quoteSign = match2.group(1) if match2 else ''
        replacement = quoteSign
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]

    while True:
        match = re.search( '<closer ([^/>]*?)sID="([^/>]+?)"([^/>]*?)/>(.*?)<closer ([^/>]*?)eID="([^/>]+?)"([^/>]*?)/>', verseLine )
        if not match: break
        attributes1, sID, words, attributes2, eID = match.group(1) + match.group(3), match.group(2), match.group(4), match.group(5) + match.group(7), match.group(6)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Closer attributes1={!r} words={!r}'.format( attributes1, words ) )
        replacement = '\\sig {}\\sig*'.format( words )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<note ([^/>]*?)swordFootnote="([^/>]+?)"([^/>]*?)>(.*?)</note>', verseLine )
        if not match: break
        attributes, number, noteContents = match.group(1)+match.group(3), match.group(2), match.group(4)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Note attributes={!r} Number={!r}'.format( attributes, number ) )
        if 'crossReference' in attributes:
            assert noteContents == ''
            replacement = '\\x {}\\x*'.format( number )
        else: halt
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<note([^/>]*?)>(.*?)</note>', verseLine )
        if not match: break
        attributes, noteContents = match.group(1), match.group(2).rstrip().replace( '\\NL**\\q1\\NL**', '//' ) # was <l />
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Note attributes={!r} contents={!r}'.format( attributes, noteContents ) )
        replacement = '\\f + \\ft {}\\f*'.format( noteContents )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<abbr([^/>]*?)>(.*?)</abbr>', verseLine )
        if not match: break
        attributes, abbr = match.group(1), match.group(2)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Abbr attributes={!r} abbr={!r}'.format( attributes, abbr ) )
        replacement = '{}'.format( abbr )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<a ([^/>]*?)href="([^>]+?)"([^/>]*?)>(.+?)</a>', verseLine )
        if not match: break
        attributes, linkHREF, linkContents = match.group(1)+match.group(3), match.group(2), match.group(4)
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( 'Link attributes={!r} HREF={!r} contents={!r}'.format( attributes, linkHREF, linkContents ) )
        replacement = linkContents
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]

    # Now scan for remaining fixed open and close fields
    replacementList = [
            ('<seg><divineName>','\\nd ','</divineName></seg>','\\nd*'),
            ('<seg><transChange type="added">','\\add ','</transChange></seg>','\\add*'),
            #('<transChange type="added">','\\add ','</transChange>','\\add*'),
            ('<catchWord>','\\add ','</catchWord>','\\add*'), # Not sure what this one is???
            #('<hi type="bold">','\\bd ','</hi>','\\bd*'),
            ('<speaker>','\\sp ','</speaker>','\\sp*'),
            ('<inscription>','\\bdit ','</inscription>','\\bdit*'), # What should this really be?
            ('<milestone type="x-idiom-start"/>','\\bdit ','<milestone type="x-idiom-end"/>','\\bdit*'), # What should this really be?
            ('<seg>','','</seg>',''), # Just remove these left-overs
            ('<foreign>','\\tl ','</foreign>','\\tl*'),
            ('<i>','\\it ','</i>','\\it*'),
            ]
    if '<divineName>' in verseLine:
        replacementList.append( ('<divineName>','\\nd ','</divineName>','\\nd*') )
    else: replacementList.append( ('<divineName type="x-yhwh">','\\nd ','</divineName>','\\nd*') )
    if '<transChange>' in verseLine:
        replacementList.append( ('<transChange>','\\add ','</transChange>','\\add*') )
    else: replacementList.append( ('<transChange type="added">','\\add ','</transChange>','\\add*') )
    verseLine = replaceFixedPairs( replacementList, verseLine )

    # Check for anything left that we should have caught above
    if '<' in verseLine or '>' in verseLine:
        print( "filterOSISVerseLine {} {} {}:{} verseLine={!r}".format( moduleName, BBB, C, V, verseLine ) )
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            if BBB!='PSA' or V not in ('1','5',): print( "Stopped at", moduleName, BBB, C, V ); halt
    #if V == '3': halt

    return verseLine
# end of filterOSISVerseLine

def importOSISVerseLine( osisVerseString, thisBook, moduleName, BBB, C, V ):
    """
    Given a verse entry string made up of OSIS segments,
        convert it into our internal format
        and add the line(s) to thisBook.

    moduleName, BBB, C, V are just used for more helpful error/information messages.

    OSIS is a pig to extract the information out of,
        but we use it nevertheless because it's the native format
        and hence most likely to represent the original well.

    We use \\NL** as an internal code for a newline
        to show where a verse line needs to be broken into internal chunks.

    Adds the line(s) to thisBook. No return value.
    """
    if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
        print( "\nimportOSISVerseLine( {} {} {}:{} … {!r} )".format( moduleName, BBB, C, V, osisVerseString ) )

    verseLine = filterOSISVerseLine( osisVerseString, moduleName, BBB, C, V )

    # Now divide up lines and enter them
    location = '{} {} {}:{} {!r}'.format( moduleName, BBB, C, V, osisVerseString ) if debuggingThisModule else '{} {} {}:{}'.format( moduleName, BBB, C, V )
    if verseLine or V != '0':
        thisBook.addVerseSegments( V, verseLine, location )
# end of importOSISVerseLine



def filterGBFVerseLine( gbfVerseString, moduleName, BBB, C, V ):
    """
    Given a verse entry string made up of GBF (General Bible Format) segments,
        convert it into our internal format.

    moduleName, BBB, C, V are just used for more helpful error/information messages.

    We use \\NL** as an internal code for a newline
        to show where a verse line needs to be broken into internal chunks.

    Return the verse line(s).
    """
    if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
        print( "\nfilterGBFVerseLine( {} {} {}:{} … {!r} )".format( moduleName, BBB, C, V, gbfVerseString ) )

    verseLine = gbfVerseString

    if moduleName == 'ASV': # Fix a module bug
        verseLine = verseLine.replace( 'pit of the<RF>1<Rf> shearing', 'pit of the<RF>2<Rf> shearing' )

    # Scan for footnote callers and callees
    lastCalled = None
    contentsDict = {}
    while True:
        match1 = re.search( '<RF>(\d{1,2}?)<Rf>', verseLine ) # Footnote caller
        if not match1: break
        caller = match1.group(1)
        match2 = re.search( '<RF>(\d{1,2}?)\\)? (.+?)<Rf>', verseLine ) # Footnote text starts with 1) or just 1
        if not match2:
            match3 = re.search( '<RF>([^\d].+?)<Rf>', verseLine )
        if match1 or match2: assert match1 and (match2 or lastCalled or match3)
        #if not match1: break
        #caller = int(match1.group(1))
        if caller in contentsDict: # We have a repeat of a previous caller
            replacement1 = '\\f + \\ft {}\\f*'.format( contentsDict[caller] )
            #print( 'replacement1 (repeat)', caller, repr(replacement1), contentsDict )
            verseLine = verseLine[:match1.start()] + replacement1 + verseLine[match1.end():]
        elif match2: # normal case -- let's separate out all of the numbered callees
            callee, contents = match2.group(1), match2.group(2).rstrip()
            if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
                print( 'FN caller={!r} callee={!r} contents={!r} {}'.format( caller, callee, contents, contentsDict ) )
            replacement2 = '{}) {}'.format( callee, contents )
            j = 0
            while replacement2:
                #print( 'Loop {} start: now {} with replacement2={!r}'.format( j, contentsDict, replacement2 ) )
                match8 = re.search( '(\d{1,2})\\) (.*?)(\d{1,2})\\) ', replacement2 )
                match9 = re.search( '(\d{1,2})\\) ', replacement2 )
                if match8: assert match9 and match9.group(1)==match8.group(1)
                if not match9: break
                if match8: callee8a, contents8, callee8b = match8.group(1), match8.group(2), match8.group(3)
                callee9 = match9.group(1)
                if match8: # We have two parts
                    assert callee8a == callee9
                    contentsDict[callee9] = contents8
                    replacement2 = replacement2[match8.end()-2-len(callee8b):]
                    #print( 'Loop {} with match8: now {} with replacement={!r}'.format( j, contentsDict, replacement2 ) )
                else: # We only have one part
                    #print( repr(callee9), repr(callee) )
                    #assert callee9 == callee
                    contentsDict[callee9] = replacement2[len(callee9)+2:]
                    replacement2 = ''
                    #print( 'Loop {} with no match8: now {} with replacement={!r}'.format( j, contentsDict, replacement2 ) )
                j += 1
            if j==0: # We found nothing above
                contentsDict[callee] = contents
                replacement2 = ''
            replacement1 = '\\f + \\ft {}\\f*'.format( contentsDict[caller] )
            assert match2.start()>match1.start() and match2.end()>match1.end() and match2.start()>match1.end()
            verseLine = verseLine[:match1.start()] + replacement1 + \
                        verseLine[match1.end():match2.start()] + replacement2 + verseLine[match2.end():]
        elif match3: # We have a callee without a number
            assert caller == '1' # Would only work for a single footnote I think
            callee, contents = caller, match3.group(1).rstrip()
            contentsDict[caller] = contents
            if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
                print( 'FN caller={!r} unnumbered contents={!r}'.format( caller, contents ) )
            nextOne = ' {}) '.format( int(caller)+1 )
            if nextOne in contents: # It contains the next footnote(s) as well
                halt # Not expected
            else:
                replacement3 = ''
            replacement1 = '\\f + \\ft {}\\f*'.format( contentsDict[caller] )
            #print( 'replacement1', repr(replacement1) )
            #print( 'replacement3', repr(replacement3) )
            assert match3.start()>match1.start() and match3.end()>match1.end() and match3.start()>match1.end()
            verseLine = verseLine[:match1.start()] + replacement1 + \
                        verseLine[match1.end():match3.start()] + replacement3 + verseLine[match3.end():]
        else:
            print( 'WHY FN caller={!r} callee={!r} contents={!r} {}'.format( caller, callee, contents, contentsDict ) )
            halt
        #print( repr(verseLine ) )
        lastCalled = callee, contents
    while True:
        match4 = re.search( '<RF>(.+?)<Rf>', verseLine ) # Footnote that doesn't match the above system
        if not match4: break
        contents = match4.group(1)
        #print( 'match4', repr(contents), repr(verseLine), contentsDict )
        #assert len(contents) > 2 and not contents[0].isdigit()
        replacement4 = '\\f + \\ft {}\\f*'.format( contents )
        #print( 'replacement4', repr(replacement4) )
        verseLine = verseLine[:match4.start()] + replacement4 + verseLine[match4.end():]

    while True:
        match = re.search( '<WT(.+?)>', verseLine ) # What's this
        if not match: break
        replacement = '' # TEMP .................................... xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        #print( 'replacement1', repr(replacement1) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<WH0(\d{1,4})>', verseLine ) # Found in rwebster
        if not match: break
        replacement = '\\str H{} \\str*'.format( match.group( 1 ) )
        #print( 'replacement1', repr(replacement1) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<WG(\d{1,4})>', verseLine ) # Found in rwebster
        if not match: break
        replacement = '\\str G{} \\str*'.format( match.group( 1 ) )
        #print( 'replacement1', repr(replacement1) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]

    # Now scan for fixed open and close fields
    replacementList = ( ('<FI>','\\it ','<Fi>','\\it*'),
                        ('<FO><FO>','\\NL**\\d ','<Fo><Fo>','\\NL**'),
                        ('<FO>','\\em ','<Fo>','\\em*'),
                        )
    verseLine = replaceFixedPairs( replacementList, verseLine )

    # Straight substitutions
    for old, new in (( '<CM>', '\\NL**\\p\\NL**' ),
                     ( '<Fo>', '\\NL**' ), # Handle left-overs
                     ( '\n', '\\NL**' ),
                      ):
        verseLine = verseLine.replace( old, new )

    # Check for anything left that we should have caught above
    if '<' in verseLine or '>' in verseLine:
        print( "filterGBFVerseLine {} {} {}:{} verseLine={!r}".format( moduleName, BBB, C, V, verseLine ) )
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( "Stopped at", moduleName, BBB, C, V ); halt

    return verseLine
# end of filterGBFVerseLine

def importGBFVerseLine( gbfVerseString, thisBook, moduleName, BBB, C, V ):
    """
    Given a verse entry string made up of GBF (General Bible Format) segments,
        convert it into our internal format
        and add the line(s) to thisBook.

    moduleName, BBB, C, V are just used for more helpful error/information messages.

    We use \\NL** as an internal code for a newline
        to show where a verse line needs to be broken into internal chunks.

    Adds the line(s) to thisBook. No return value.
    """
    if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
        print( "\nimportGBFVerseLine( {} {} {}:{} … {!r} )".format( moduleName, BBB, C, V, gbfVerseString ) )

    verseLine = filterGBFVerseLine( gbfVerseString, moduleName, BBB, C, V )

    # Now divide up lines and enter them
    location = '{} {} {}:{} {!r}'.format( moduleName, BBB, C, V, gbfVerseString ) if debuggingThisModule else '{} {} {}:{}'.format( moduleName, BBB, C, V )
    thisBook.addVerseSegments( V, verseLine, location )
# end of importGBFVerseLine



def filterTHMLVerseLine( thmlVerseString, moduleName, BBB, C, V ):
    """
    Given a verse entry string made up of THML segments,
        convert it into our internal format.

    moduleName, BBB, C, V are just used for more helpful error/information messages.

    We use \\NL** as an internal code for a newline
        to show where a verse line needs to be broken into internal chunks.

    Returns the verse line(s).
    """
    if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
        print( "\nfilterTHMLVerseLine( {} {} {}:{} … {!r} )".format( moduleName, BBB, C, V, thmlVerseString ) )
    verseLine = thmlVerseString

    # Regular expression substitutions
    while True:
        match = re.search( '<div class="title">(.+?)</div>', verseLine )
        if not match: break
        replacement = '\\mt {}'.format( match.group(1) )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<div class="sechead">(.+?)</div>', verseLine )
        if not match: break
        replacement = '\\s {}'.format( match.group(1) )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    #while True:
        #match = re.search( '<scripRef>(.+?)</scripRef>', verseLine )
        #if not match: break
        #replacement = '\\x {}\\x*'.format( match.group(1) )
        ##print( 'replacement', repr(replacement) )
        #verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<scripRef([^/>]+?)>(.+?)</scripRef>', verseLine )
        if not match: break
        attributes, contents = match.group(1), match.group(2)
        #print( 'match   attrs={!r}   contents={!r}'.format( attributes, contents ) )
        matcha = re.search( 'passage="(.+?)"', attributes )
        passage = matcha.group(1) if matcha else ''
        matchb = re.search( 'version="(.+?)"', attributes )
        version = matchb.group(1) if matchb else ''
        #print( 'match1   passage={!r}   version={!r}'.format( passage, version ) )
        replacement = '\\x - \\xo {} \\xt {} {} \\x*'.format( contents, version, passage )
        #print( 'replacement', repr(replacement) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]
    while True:
        match = re.search( '<WT(.+?)>', verseLine ) # What's this
        if not match: break
        replacement = '' # TEMP .................................... xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        #print( 'replacement1', repr(replacement1) )
        verseLine = verseLine[:match.start()] + replacement + verseLine[match.end():]

    # Straight substitutions
    for old, new in ( ( '<br />', '\\NL**' ), ( '<br/>', '\\NL**' ),
                      ):
        verseLine = verseLine.replace( old, new )

    # Now scan for fixed open and close fields
    replacementList = ( ('<font color="#ff0000">','\\wj ', '</font>','\\wj*'),
                        ( '<small>', '\\sc ', '</small>', '\\sc*' ),
                        ( '<note>', '\\f ', '</note>', '\\f*' ),
                        ( '<scripRef>', '\\x ', '</scripRef>', '\\x*' ),
                        ( '<i>', '\\it ', '</i>', '\\it*' ),
                        ( '<sup>', '\\ord ', '</sup>', '\\ord*' ), # Ord is the best we have for superscript
                        )
    verseLine = replaceFixedPairs( replacementList, verseLine )

    # Check for anything left that we should have caught above
    if '<' in verseLine or '>' in verseLine:
        print( "filterTHMLVerseLine: {} {} {}:{} verseLine={!r}".format( moduleName, BBB, C, V, verseLine ) )
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule: print( "Stopped at", moduleName, BBB, C, V ); halt

    return verseLine
# end of filterTHMLVerseLine

def importTHMLVerseLine( thmlVerseString, thisBook, moduleName, BBB, C, V ):
    """
    Given a verse entry string made up of THML segments,
        convert it into our internal format
        and add the line(s) to thisBook.

    moduleName, BBB, C, V are just used for more helpful error/information messages.

    We use \\NL** as an internal code for a newline
        to show where a verse line needs to be broken into internal chunks.

    Adds the line(s) to thisBook. No return value.
    """
    if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
        print( "\nimportTHMLVerseLine( {} {} {}:{} … {!r} )".format( moduleName, BBB, C, V, thmlVerseString ) )

    verseLine = importTHMLVerseLine( thmlVerseString, moduleName, BBB, C, V )

    # Now divide up lines and enter them
    location = '{} {} {}:{} {!r}'.format( moduleName, BBB, C, V, thmlVerseString ) if debuggingThisModule else '{} {} {}:{}'.format( moduleName, BBB, C, V )
    thisBook.addVerseSegments( V, verseLine, location )
# end of importTHMLVerseLine



class SwordKey( SimpleVerseKey ):
    """
    Just a SimpleVerseKey class (with BBB, C, V, optional S)
        with a couple of calls compatible with the SwordKey class.
    """
    def getChapter( self ):
        return self.getChapterNumberInt()

    def getVerse( self ):
        return self.getVerseNumberInt()
# end of class SwordKey



class SwordInterface():
    """
    This is the interface class that we use between our higher level code
        and the code reading the actual installed Sword modules.
    """
    def __init__( self ):
        """
        """
        if SwordType == 'CrosswireLibrary':
            self.library = Sword.SWMgr()
            #self.keyCache = {}
            #self.verseCache = {}
        elif SwordType == 'OurCode':
            self.library = SwordModules.SwordModules() # Loads all of conf files that it can find
            if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
                print( 'Sword library', self.library )
    # end of SwordInterface.__init__


    def getAvailableModuleCodes( self, onlyModuleTypes=None ):
        """
        Module type is a list of strings for the type(s) of modules to include.

        Returns a list of available Sword module codes.
        """
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( exp("SwordInterface.getAvailableModuleCodes( {} )").format( onlyModuleTypes ) )

        if SwordType == 'CrosswireLibrary':
            availableModuleCodes = []
            for j,moduleBuffer in enumerate(self.library.getModules()):
                moduleID = moduleBuffer.getRawData()
                #module = self.library.getModule( moduleID )
                #if 0:
                    #print( "{} {} ({}) {} {!r}".format( j, module.getName(), module.getType(), module.getLanguage(), module.getEncoding() ) )
                    #try: print( "    {} {!r} {} {}".format( module.getDescription(), module.getMarkup(), module.getDirection(), "" ) )
                    #except UnicodeDecodeError: print( "   Description is not Unicode!" )
                print( "moduleID", repr(moduleID) )
                availableModuleCodes.append( moduleID )
            return availableModuleCodes
        elif SwordType == 'OurCode':
            return self.library.getAvailableModuleCodes( onlyModuleTypes )
    # end of SwordInterface.getAvailableModuleCodes


    def getAvailableModuleCodeDuples( self, onlyModuleTypes=None ):
        """
        Module type is a list of strings for the type(s) of modules to include.

        Returns a list of 2-tuples (duples) containing module abbreviation and type
        """
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( exp("SwordInterface.getAvailableModuleCodeDuples( {} )").format( onlyModuleTypes ) )

        if SwordType == 'CrosswireLibrary':
            availableModuleCodes = []
            for j,moduleBuffer in enumerate(self.library.getModules()):
                moduleID = moduleBuffer.getRawData()
                module = self.library.getModule( moduleID )
                moduleType = module.getType()
                #if 1:
                    #print( "{} {} ({}) {} {!r}".format( j, module.getName(), module.getType(), module.getLanguage(), module.getEncoding() ) )
                    #try: print( "    {} {!r} {} {}".format( module.getDescription(), module.getMarkup(), module.getDirection(), "" ) )
                    #except UnicodeDecodeError: print( "   Description is not Unicode!" )
                #print( "moduleID", repr(moduleID), repr(moduleType) )
                assert moduleType in ( 'Biblical Texts', 'Commentaries', 'Lexicons / Dictionaries', 'Generic Books' )
                if onlyModuleTypes is None or moduleType in onlyModuleTypes:
                    availableModuleCodes.append( (moduleID,moduleType) )
            return availableModuleCodes
        elif SwordType == 'OurCode':
            result1 = self.library.getAvailableModuleCodeDuples( onlyModuleTypes )
            #print( 'getAvailableModuleCodeDuples.result1', result1 )
            if result1:
                result2 = [(name,SwordModules.GENERIC_SWORD_MODULE_TYPE_NAMES[modType]) for name,modType in result1]
                #print( 'getAvailableModuleCodeDuples.result2', result2 )
                return result2
    # end of SwordInterface.getAvailableModuleCodeDuples


    def getModule( self, moduleAbbreviation='KJV' ):
        """
        """
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( "SwordInterface.getModule( {} )".format( moduleAbbreviation ) )

        if SwordType == 'CrosswireLibrary':
            #print( "gM", module.getName() )
            result1 = self.library.getModule( moduleAbbreviation )
            #print( 'getModule.result1', result1 )
            if result1 is not None: return result1
            # Try again with a capital
            result2 = self.library.getModule( moduleAbbreviation.title() )
            #print( 'getModule.result2', result2 )
            return result2
        elif SwordType == 'OurCode':
            lmResult = self.library.loadModule( moduleAbbreviation ) # e.g., KJV
            #except KeyError: lmResult = self.library.loadBooks( moduleAbbreviation.lower() ) # needs kjv??? why? what changed?
            #print( moduleAbbreviation, lmResult ); halt
            resultFlag, theModule = lmResult
            #if debuggingThisModule and not resultFlag: print( "failed here!" ); halt
            return theModule
    # end of SwordInterface.getModule


    def loadBook( self, BBB, BibleObject, moduleAbbreviation='KJV' ):
        """
        Load the given book from a Sword Module into the given BibleObject.
        """
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( "SwordInterface.loadBook( {}, …, {} )".format( BBB, moduleAbbreviation ) )
            assert BBB not in BibleObject

        module = self.getModule( moduleAbbreviation )
        if module is None:
            logging.critical( _("Unable to load {!r} module -- not known by Sword").format( moduleAbbreviation ) )
            return

        self.triedLoadingBook[BBB] = True
        self.bookNeedsReloading[BBB] = False

        # Create the new book
        if BibleOrgSysGlobals.verbosityLevel > 2:  print( '  Loading {} {}…'.format( moduleAbbreviation, BBB ) )
        thisBook = BibleBook( self, BBB )
        thisBook.objectNameString = 'Sword Bible Book object'
        thisBook.objectTypeString = 'Sword Bible'
        currentC, haveText = '0', False

        if SwordType=='CrosswireLibrary': # need to load the module
            markupCode = ord( module.getMarkup() )
            encoding = ord( module.getEncoding() )
            if encoding == ENC_LATIN1: BibleObject.encoding = 'latin-1'
            elif encoding == ENC_UTF8: BibleObject.encoding = 'utf-8'
            elif encoding == ENC_UTF16: BibleObject.encoding = 'utf-16'
            elif BibleOrgSysGlobals.debugFlag and debuggingThisModule: halt

            if BibleOrgSysGlobals.verbosityLevel > 3:
                print( 'Description: {!r}'.format( module.getDescription() ) )
                print( 'Direction: {!r}'.format( ord(module.getDirection()) ) )
                print( 'Encoding: {!r}'.format( encoding ) )
                print( 'Language: {!r}'.format( module.getLanguage() ) )
                print( 'Markup: {!r}={}'.format( markupCode, FMT_DICT[markupCode] ) )
                print( 'Name: {!r}'.format( module.getName() ) )
                print( 'RenderHeader: {!r}'.format( module.getRenderHeader() ) )
                print( 'Type: {!r}'.format( module.getType() ) )
                print( 'IsSkipConsecutiveLinks: {!r}'.format( module.isSkipConsecutiveLinks() ) )
                print( 'IsUnicode: {!r}'.format( module.isUnicode() ) )
                print( 'IsWritable: {!r}'.format( module.isWritable() ) )
                #return

# UNFINISHED
            for index in range( 0, 999999 ):
                module.setIndex( index )
                if module.getIndex() != index: break # Gone too far

                # Find where we're at
                verseKey = module.getKey()
                verseKeyText = verseKey.getShortText()
                #if '2' in verseKeyText: halt # for debugging first verses
                #if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
                    #print( '\nvkst={!r} vkix={}'.format( verseKeyText, verseKey.getIndex() ) )

                #nativeVerseText = module.renderText().decode( self.encoding, 'replace' )
                #nativeVerseText = str( module.renderText() ) if self.encoding=='utf-8' else str( module.renderText(), encoding=self.encoding )
                #print( 'getRenderHeader: {} {!r}'.format( len(module.getRenderHeader()), module.getRenderHeader() ) )
                #print( 'stripText: {} {!r}'.format( len(module.stripText()), module.stripText() ) )
                #print( 'renderText: {} {!r}'.format( len(str(module.renderText())), str(module.renderText()) ) )
                #print( 'getRawEntry: {} {!r}'.format( len(module.getRawEntry()), module.getRawEntry() ) )
                try: nativeVerseText = module.getRawEntry()
                #try: nativeVerseText = str( module.renderText() )
                except UnicodeDecodeError: nativeVerseText = ''

                if ':' not in verseKeyText:
                    if BibleOrgSysGlobals.debugFlag and BibleOrgSysGlobals.verbosityLevel > 2:
                        print( "Unusual Sword verse key: {} (gave {!r})".format( verseKeyText, nativeVerseText ) )
                    if BibleOrgSysGlobals.debugFlag:
                        assert verseKeyText in ( '[ Module Heading ]', '[ Testament 1 Heading ]', '[ Testament 2 Heading ]', )
                    if BibleOrgSysGlobals.verbosityLevel > 3:
                        if markupCode == FMT_OSIS:
                            match = re.search( '<milestone ([^/>]*?)type="x-importer"([^/>]*?)/>', nativeVerseText )
                            if match:
                                attributes = match.group(1) + match.group(2)
                                match2 = re.search( 'subType="(.+?)"', attributes )
                                subType = match2.group(1) if match2 else None
                                if subType and subType.startswith( 'x-' ): subType = subType[2:] # Remove the x- prefix
                                match2 = re.search( 'n="(.+?)"', attributes )
                                n = match2.group(1) if match2 else None
                                if n: n = n.replace( '$', '' ).strip()
                                print( "Module created by {} {}".format( subType, n ) )
                    continue
                vkBits = verseKeyText.split()
                assert len(vkBits) == 2
                osisBBB = vkBits[0]
                BBB = BibleOrgSysGlobals.BibleBooksCodes.getBBBFromOSIS( osisBBB )
                if isinstance( BBB, list ): BBB = BBB[0] # We sometimes get a list of options -- take the first = most likely one
                vkBits = vkBits[1].split( ':' )
                assert len(vkBits) == 2
                C, V = vkBits
                #print( 'At {} {}:{}'.format( BBB, C, V ) )

                if C != currentC:
                    thisBook.addLine( 'c', C )
                    #if C == '2': halt
                    currentC = C

                if nativeVerseText:
                    haveText = True
                    if markupCode == FMT_OSIS: importOSISVerseLine( nativeVerseText, thisBook, moduleAbbreviation, BBB, C, V )
                    elif markupCode == FMT_GBF: importGBFVerseLine( nativeVerseText, thisBook, moduleAbbreviation, BBB, C, V )
                    elif markupCode == FMT_THML: importTHMLVerseLine( nativeVerseText, thisBook, moduleAbbreviation, BBB, C, V )
                    else:
                        print( 'markupCode', repr(markupCode) )
                        if BibleOrgSysGlobals.debugFlag: halt
                        return

            if haveText: # Save the book
                if BibleOrgSysGlobals.verbosityLevel > 3: print( "Saving", moduleAbbreviation, currentBBB, bookCount )
                BibleObject.saveBook( thisBook )


        elif SwordType=='OurCode': # module is already loaded above in getModule call
            #print( "moduleConfig =", module.SwordModuleConfiguration )
            BibleObject.books = module.books
    # end of SwordInterface.loadBook


    def loadBooks( self, BibleObject, moduleAbbreviation='KJV' ):
        """
        Load all the books from a Sword Module into the given BibleObject.
        """
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( "SwordInterface.loadBooks( …, {} )".format( moduleAbbreviation ) )

        module = self.getModule( moduleAbbreviation )
        if module is None:
            logging.critical( _("Unable to load {!r} module -- not known by Sword").format( moduleAbbreviation ) )
            return

        if SwordType=='CrosswireLibrary': # need to load the module
            markupCode = ord( module.getMarkup() )
            encoding = ord( module.getEncoding() )
            if encoding == ENC_LATIN1: BibleObject.encoding = 'latin-1'
            elif encoding == ENC_UTF8: BibleObject.encoding = 'utf-8'
            elif encoding == ENC_UTF16: BibleObject.encoding = 'utf-16'
            elif BibleOrgSysGlobals.debugFlag and debuggingThisModule: halt

            if BibleOrgSysGlobals.verbosityLevel > 3:
                print( 'Description: {!r}'.format( module.getDescription() ) )
                print( 'Direction: {!r}'.format( ord(module.getDirection()) ) )
                print( 'Encoding: {!r}'.format( encoding ) )
                print( 'Language: {!r}'.format( module.getLanguage() ) )
                print( 'Markup: {!r}={}'.format( markupCode, FMT_DICT[markupCode] ) )
                print( 'Name: {!r}'.format( module.getName() ) )
                print( 'RenderHeader: {!r}'.format( module.getRenderHeader() ) )
                print( 'Type: {!r}'.format( module.getType() ) )
                print( 'IsSkipConsecutiveLinks: {!r}'.format( module.isSkipConsecutiveLinks() ) )
                print( 'IsUnicode: {!r}'.format( module.isUnicode() ) )
                print( 'IsWritable: {!r}'.format( module.isWritable() ) )
                #return

            bookCount = 0
            currentBBB = None
            for index in range( 0, 999999 ):
                module.setIndex( index )
                if module.getIndex() != index: break # Gone too far

                # Find where we're at
                verseKey = module.getKey()
                verseKeyText = verseKey.getShortText()
                #if '2' in verseKeyText: halt # for debugging first verses
                #if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
                    #print( '\nvkst={!r} vkix={}'.format( verseKeyText, verseKey.getIndex() ) )

                #nativeVerseText = module.renderText().decode( self.encoding, 'replace' )
                #nativeVerseText = str( module.renderText() ) if self.encoding=='utf-8' else str( module.renderText(), encoding=self.encoding )
                #print( 'getRenderHeader: {} {!r}'.format( len(module.getRenderHeader()), module.getRenderHeader() ) )
                #print( 'stripText: {} {!r}'.format( len(module.stripText()), module.stripText() ) )
                #print( 'renderText: {} {!r}'.format( len(str(module.renderText())), str(module.renderText()) ) )
                #print( 'getRawEntry: {} {!r}'.format( len(module.getRawEntry()), module.getRawEntry() ) )
                try: nativeVerseText = module.getRawEntry()
                #try: nativeVerseText = str( module.renderText() )
                except UnicodeDecodeError: nativeVerseText = ''

                if ':' not in verseKeyText:
                    if BibleOrgSysGlobals.debugFlag and BibleOrgSysGlobals.verbosityLevel > 2:
                        print( "Unusual Sword verse key: {} (gave {!r})".format( verseKeyText, nativeVerseText ) )
                    if BibleOrgSysGlobals.debugFlag:
                        assert verseKeyText in ( '[ Module Heading ]', '[ Testament 1 Heading ]', '[ Testament 2 Heading ]', )
                    if BibleOrgSysGlobals.verbosityLevel > 3:
                        if markupCode == FMT_OSIS:
                            match = re.search( '<milestone ([^/>]*?)type="x-importer"([^/>]*?)/>', nativeVerseText )
                            if match:
                                attributes = match.group(1) + match.group(2)
                                match2 = re.search( 'subType="(.+?)"', attributes )
                                subType = match2.group(1) if match2 else None
                                if subType and subType.startswith( 'x-' ): subType = subType[2:] # Remove the x- prefix
                                match2 = re.search( 'n="(.+?)"', attributes )
                                n = match2.group(1) if match2 else None
                                if n: n = n.replace( '$', '' ).strip()
                                print( "Module created by {} {}".format( subType, n ) )
                    continue
                vkBits = verseKeyText.split()
                assert len(vkBits) == 2
                osisBBB = vkBits[0]
                BBB = BibleOrgSysGlobals.BibleBooksCodes.getBBBFromOSIS( osisBBB )
                if isinstance( BBB, list ): BBB = BBB[0] # We sometimes get a list of options -- take the first = most likely one
                vkBits = vkBits[1].split( ':' )
                assert len(vkBits) == 2
                C, V = vkBits
                #print( 'At {} {}:{}'.format( BBB, C, V ) )

                # Start a new book if necessary
                if BBB != currentBBB:
                    if currentBBB is not None and haveText: # Save the previous book
                        if BibleOrgSysGlobals.verbosityLevel > 3: print( "Saving", currentBBB, bookCount )
                        self.saveBook( thisBook )
                    # Create the new book
                    if BibleOrgSysGlobals.verbosityLevel > 2:  print( '  Loading {} {}…'.format( moduleAbbreviation, BBB ) )
                    thisBook = BibleBook( self, BBB )
                    thisBook.objectNameString = 'Sword Bible Book object'
                    thisBook.objectTypeString = 'Sword Bible'
                    currentBBB, currentC, haveText = BBB, '0', False
                    bookCount += 1

                if C != currentC:
                    thisBook.addLine( 'c', C )
                    #if C == '2': halt
                    currentC = C

                if nativeVerseText:
                    haveText = True
                    if markupCode == FMT_OSIS: importOSISVerseLine( nativeVerseText, thisBook, moduleAbbreviation, BBB, C, V )
                    elif markupCode == FMT_GBF: importGBFVerseLine( nativeVerseText, thisBook, moduleAbbreviation, BBB, C, V )
                    elif markupCode == FMT_THML: importTHMLVerseLine( nativeVerseText, thisBook, moduleAbbreviation, BBB, C, V )
                    else:
                        print( 'markupCode', repr(markupCode) )
                        if BibleOrgSysGlobals.debugFlag: halt
                        return

            if currentBBB is not None and haveText: # Save the very last book
                if BibleOrgSysGlobals.verbosityLevel > 3: print( "Saving", moduleAbbreviation, currentBBB, bookCount )
                BibleObject.saveBook( thisBook )


        elif SwordType=='OurCode': # module is already loaded above in getModule call
            #print( "moduleConfig =", module.SwordModuleConfiguration )
            BibleObject.books = module.books
    # end of SwordInterface.loadBooks


    def makeKey( self, BBB, C, V ):
        #if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            #print( "SwordInterface.makeKey( {} {}:{} )".format( BBB, C, V ) )

        #if BCV  in self.keyCache:
            #print( "Cached", BCV )
            #return self.keyCache[BCV]
        if SwordType == 'CrosswireLibrary':
            B = BibleOrgSysGlobals.BibleBooksCodes.getOSISAbbreviation( BBB )
            refString = "{} {}:{}".format( B, C, V )
            #print( 'refString', refString )
            verseKey = Sword.VerseKey( refString )
            #self.keyCache[BCV] = verseKey
            return verseKey
        elif SwordType == 'OurCode':
            return SwordKey( BBB, C, V )
    # end of SwordInterface.makeKey


    def getContextVerseData( self, module, key ):
        """
        Returns a InternalBibleEntryList of 5-tuples, e.g.,
            [
            ('c', 'c', '1', '1', []),
            ('c#', 'c', '1', '1', []),
            ('v', 'v', '1', '1', []),
            ('v~', 'v~', 'In the beginning God created the heavens and the earth.',
                                    'In the beginning God created the heavens and the earth.', [])
            ]
        """
        if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            print( exp("SwordInterface.getContextVerseData( {}, {} )").format( module.getName(), key.getShortText() ) )

        if SwordType == 'CrosswireLibrary':
            if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
                mm = module.getMarkup()
                print( "  module markup", repr(mm), SWORD_MARKUPS[ord(mm)] )
            try: verseText = module.stripText( key )
            except UnicodeDecodeError:
                print( "Can't decode utf-8 text of {} {}".format( module.getName(), key.getShortText() ) )
                return
            if '\n' in verseText or '\r' in verseText: # Why!!!
                if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
                    print( exp("getVerseData: Why does it have CR or LF in {} {} {}") \
                            .format( module.getName(), key.getShortText(), repr(verseText) ) )
                verseText = verseText.replace( '\n', '' ).replace( '\r', '' )
            verseText = verseText.rstrip()
            #print( 'verseText', repr(verseText) )
            verseData = InternalBibleEntryList()
            #c, v = key.getChapterNumberStr(), key.getVerseNumberStr()
            cv = key.getShortText().split( ' ', 1 )[1]
            c, v = cv.split( ':', 1 )
            #print( 'c,v', repr(c), repr(v) )
            # Prepend the verse number since Sword modules don't contain that info in the data
            if v=='1': verseData.append( InternalBibleEntry( 'c#','c', c, c, None, c ) )
            verseData.append( InternalBibleEntry( 'v','v', v, v, None, v ) )
            verseData.append( InternalBibleEntry( 'v~','v~', verseText, verseText, None, verseText ) )
            contextVerseData = verseData, [] # No context
        elif SwordType == 'OurCode':
            #print( exp("module"), module )
            try: contextVerseData = module.getContextVerseData( key )
            except KeyError: # Just create a blank verse entry
                verseData = InternalBibleEntryList()
                c, v = key.getChapterNumberStr(), key.getVerseNumberStr()
                if v=='1': verseData.append( InternalBibleEntry( 'c#','c', c, c, None, c ) )
                verseData.append( InternalBibleEntry( 'v','v', v, v, None, v ) )
                contextVerseData = verseData, [] # No context
            #print( exp("gVD={} key={}, st={}").format( module.getName(), key, contextVerseData ) )
            if contextVerseData is None:
                if key.getChapter()!=0 or key.getVerse()!=0: # We're not surprised if there's no chapter or verse zero
                    print( exp("SwordInterface.getVerseData no VD"), module.getName(), key, contextVerseData )
                contextVerseData = [], None
            else:
                verseData, context = contextVerseData
                #print( "vD", verseData )
                #assert isinstance( verseData, InternalBibleEntryList ) or isinstance( verseData, list )
                assert isinstance( verseData, InternalBibleEntryList )
                #assert isinstance( verseData, list )
                assert 1 <= len(verseData) <= 6
        #print( verseData ); halt
        return contextVerseData
    # end of SwordInterface.getContextVerseData


    def getVerseData( self, module, key ):
        """
        Returns a list of 5-tuples, e.g.,
            [
            ('c', 'c', '1', '1', []),
            ('c#', 'c', '1', '1', []),
            ('v', 'v', '1', '1', []),
            ('v~', 'v~', 'In the beginning God created the heavens and the earth.',
                                    'In the beginning God created the heavens and the earth.', [])
            ]
        """
        if SwordType == 'CrosswireLibrary':
            try: verseText = module.stripText( key )
            except UnicodeDecodeError:
                print( "Can't decode utf-8 text of {} {}".format( module.getName(), key.getShortText() ) )
                return
            if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
                if '\n' in verseText or '\r' in verseText:
                    print( exp("getVerseData: Why does it have CR or LF in {} {}").format( module.getName(), repr(verseText) ) )
            verseData = []
            c, v = str(key.getChapter()), str(key.getVerse())
            # Prepend the verse number since Sword modules don't contain that info in the data
            if v=='1': verseData.append( ('c#','c', c, c, [],) )
            verseData.append( ('v','v', v, v, [],) )
            verseData.append( ('v~','v~', verseText, verseText, [],) )
        elif SwordType == 'OurCode':
            #print( exp("module"), module )
            stuff = module.getContextVerseData( key )
            #print( exp("gVD={} key={}, st={}").format( module.getName(), key, stuff ) )
            if stuff is None:
                print( exp("SwordInterface.getVerseData no VD"), module.getName(), key, stuff )
                assert key.getChapter()==0 or key.getVerse()==0
            else:
                verseData, context = stuff
                #print( "vD", verseData )
                #assert isinstance( verseData, InternalBibleEntryList ) or isinstance( verseData, list )
                assert isinstance( verseData, InternalBibleEntryList )
                #assert isinstance( verseData, list )
                assert 1 <= len(verseData) <= 6
        #print( verseData ); halt
        return verseData
    # end of SwordInterface.getVerseData


    def getVerseText( self, module, key ):
        """
        """
        #cacheKey = (module.getName(), key.getShortText())
        #if cacheKey in self.verseCache:
            #print( "Cached", cacheKey )
            #return self.verseCache[cacheKey]
        #if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
            #print( "SwordInterface.getVerseText({},{})".format( module.getName(), key.getText() ) )

        if SwordType == 'CrosswireLibrary':
            try: verseText = module.stripText( key )
            except UnicodeDecodeError:
                print( "Can't decode utf-8 text of {} {}".format( module.getName(), key.getShortText() ) )
                return ''
        elif SwordType == 'OurCode':
            verseData = module.getContextVerseData( key )
            #print( "gVT", module.getName(), key, verseData )
            assert isinstance( verseData, list )
            assert 2 <= len(verseData) <= 5
            verseText = ''
            for entry in verseData:
                marker, cleanText = entry.getMarker(), entry.getCleanText()
                if marker == 'c': pass # Ignore
                elif marker == 'p': verseText += '¶' + cleanText
                elif marker == 'm': verseText += '§' + cleanText
                elif marker == 'v': pass # Ignore
                elif marker == 'v~': verseText += cleanText
                else: print( "Unknown marker", marker, cleanText ); halt
        #self.verseCache[cacheKey] = verseText
        #print( module.getName(), key.getShortText(), "'"+verseText+"'" )
        return verseText
    # end of SwordInterface.getVerseText
# end of class SwordInterface


def getBCV( BCV, moduleAbbreviation='KJV' ): # Very slow -- for testing only
    """
    """
    if BibleOrgSysGlobals.debugFlag and debuggingThisModule:
        print( "SwordResources.getBCV( {}, {} )".format( BCV, moduleAbbreviation ) )

    library = Sword.SWMgr()
    module = library.getModule( moduleAbbreviation )
    refString = "{} {}:{}".format( BCV[0][:3], BCV[1], BCV[2] )
    #print( 'refString', refString )
    return module.stripText( Sword.VerseKey( refString ) )
# end of getBCV



def demo():
    """
    Sword Resources
    """
    if BibleOrgSysGlobals.verbosityLevel > 0: print( ProgNameVersion )

    #print( "\ndir Sword", dir(Sword) )

    if SwordType == 'CrosswireLibrary':
        print( "\ndir Sword.SWVersion()", dir(Sword.SWVersion()) )
        print( "Version", Sword.SWVersion().getText() )
        print( "Versions", Sword.SWVersion().major, Sword.SWVersion().minor, Sword.SWVersion().minor2, Sword.SWVersion().minor3 ) # ints

        library = Sword.SWMgr()
        #print( "\ndir library", dir(library) )
        #print( "\nlibrary getHomeDir", library.getHomeDir().getRawData() )

    def Find( attribute ):
        """
        Search for methods and attributes
        """
        print( "\nSearching for attribute {!r}…".format( attribute ) )
        found = False
        AA = attribute.upper()
        for thing in dir(Sword):
            BB = thing.upper()
            if BB.startswith(AA): print( "  Have {} in Sword".format( thing ) ); found = True
        for thing in dir(Sword.SWVersion()):
            BB = thing.upper()
            if BB.startswith(AA): print( "  Have {} in SWVersion".format( thing ) ); found = True
        for thing in dir(Sword.SWMgr()):
            BB = thing.upper()
            if BB.startswith(AA): print( "  Have {} in SWMgr".format( thing ) ); found = True
        module = library.getModule( 'KJV' )
        for thing in dir(module):
            BB = thing.upper()
            if BB.startswith(AA): print( "  Have {} in SWModule".format( thing ) ); found = True
        for thing in dir(Sword.SWKey()):
            BB = thing.upper()
            if BB.startswith(AA): print( "  Have {} in SWKey".format( thing ) ); found = True
        for thing in dir(Sword.VerseKey()):
            BB = thing.upper()
            if BB.startswith(AA): print( "  Have {} in VerseKey".format( thing ) ); found = True
        #for thing in dir(Sword.InstallMgr()):
            #BB = thing.upper()
            #if BB.startswith(AA): print( "  Have {} in InstallMgr".format( thing ) ); found = True
        for thing in dir(Sword.LocaleMgr()):
            BB = thing.upper()
            if BB.startswith(AA): print( "  Have {} in LocaleMgr".format( thing ) ); found = True
        for thing in dir(Sword.SWFilterMgr()):
            BB = thing.upper()
            if BB.startswith(AA): print( "  Have {} in SWFilterMgr".format( thing ) ); found = True
        if not found: print( " Sorry, {!r} not found.".format( attribute ) )
    # end of Find

    if 0: # Install manager
        print( "\nINSTALL MANAGER" )
        im = Sword.InstallMgr() # FAILS
        print( "\ndir im", im, dir(im) )

    if 0: # Locale manager
        print( "\nLOCALE MANAGER" )
        lm = Sword.LocaleMgr()
        print( "dir lm", lm, dir(lm) )
        print( "default {}".format( lm.getDefaultLocaleName() ) )
        print( "available {}".format( lm.getAvailableLocales() ) ) # Gives weird result: "available ()"
        print( "locale {}".format( lm.getLocale( "en" ) ) ) # Needs a string parameter but why does it return None?

    if 0: # try filters
        print( "\nFILTER MANAGER" )
        fm = Sword.SWFilterMgr()
        print( "\ndir filters", dir(fm) )

    if SwordType == 'CrosswireLibrary':
        # Get a list of available module names and types
        print( "\n{} modules are installed.".format( len(library.getModules()) ) )
        for j,moduleBuffer in enumerate(library.getModules()):
            moduleID = moduleBuffer.getRawData()
            module = library.getModule( moduleID )
            if 0:
                print( "{} {} ({}) {} {!r}".format( j, module.getName(), module.getType(), module.getLanguage(), module.getEncoding() ) )
                try: print( "    {} {!r} {} {}".format( module.getDescription(), module.getMarkup(), module.getDirection(), "" ) )
                except UnicodeDecodeError: print( "   Description is not Unicode!" )
        #print( "\n", j, "dir module", dir(module) )

        # Try some modules
        mod1 = library.getModule( 'KJV' )
        print( "\nmod1 {} ({}) {!r}".format( mod1.getName(), mod1.getType(), mod1.getDescription() ) )
        mod2 = library.getModule( 'ASV' )
        print( "\nmod2 {} ({}) {!r}".format( mod2.getName(), mod2.getType(), mod2.getDescription() ) )
        mod3 = library.getModule( 'WEB' )
        print( "\nmod3 {} ({}) {!r}".format( mod3.getName(), mod3.getType(), mod3.getDescription() ) )
        abbott = library.getModule( 'Abbott' )
        print( "\nabbott {} ({}) {!r}".format( abbott.getName(), abbott.getType(), abbott.getDescription() ) )
        strongsGreek = library.getModule( 'StrongsGreek' )
        print( "\nSG {} ({}) {!r}\n".format( strongsGreek.getName(), strongsGreek.getType(), strongsGreek.getDescription() ) )
        strongsHebrew = library.getModule( 'StrongsHebrew' )
        print( "\nSH {} ({}) {!r}\n".format( strongsHebrew.getName(), strongsHebrew.getType(), strongsHebrew.getDescription() ) )
        print()

        # Try a sword key
        sk = Sword.SWKey( "H0430" )
        #print( "\ndir sk", dir(sk) )

        # Try a verse key
        vk = Sword.VerseKey( "Jn 3:16" )
        #print( "\ndir vk", dir(vk) )
        #print( "val", vk.validateCurrentLocale() ) # gives None
        print( "getInfo", vk.getLocale(), vk.getBookCount(), vk.getBookMax(), vk.getIndex(), vk.getVersificationSystem() )
        print( "getBCV {}({}/{}) {}/{}:{} in {!r}({})/{}".format( vk.getBookName(), vk.getBookAbbrev(), vk.getOSISBookName(), vk.getChapter(), vk.getChapterMax(), vk.getVerse(), repr(vk.getTestament()), vk.getTestamentIndex(), vk.getTestamentMax() ) )
        print( "getText {} {} {} {} {!r}".format( vk.getOSISRef(), vk.getText(), vk.getRangeText(), vk.getShortText(), vk.getSuffix() ) )
        #print( "bounds {} {}".format( vk.getLowerBound(), vk.getUpperBound() ) )

        if 0: # Set a filter HOW DO WE DO THIS???
            rFs = mod1.getRenderFilters()
            print( mod1.getRenderFilters() )
            mod1.setRenderFilter()

        try: print( "\n{} {}: {}".format( mod1.getName(), "Jonny 1:1", mod1.renderText( Sword.VerseKey("Jn 1:1") ) ) )
        except UnicodeDecodeError: print( "Unicode decode error in", mod1.getName() )

        mod1.increment()
        print( "\n{} {}: {}".format( mod1.getName(), mod1.getKey().getText(), mod1.stripText(  ) ) )
        mod1.increment()
        print( "\n{} {}: {}".format( mod1.getName(), mod1.getKey().getText(), mod1.renderText(  ) ) )
        try: print( "\n{} {}: {}".format( mod2.getName(), vk.getText(), mod2.renderText( vk ) ) )
        except UnicodeDecodeError: print( "Unicode decode error in", mod2.getName() )
        try: print( "\n{} {}: {}".format( mod3.getName(), vk.getText(), mod3.renderText( vk ) ) )
        except UnicodeDecodeError: print( "Unicode decode error in", mod3.getName() )
        try: print( "\n{} {}: {}".format( mod3.getName(), vk.getText(), mod3.renderText( vk ) ) )
        except UnicodeDecodeError: print( "Unicode decode error in", mod3.getName() )

        try: print( "\n{} {}: {}".format( abbott.getName(), vk.getText(), abbott.renderText( vk ) ) )
        except UnicodeDecodeError: print( "Unicode decode error in", abbott.getName() )

        try: print( "\n{} {}: {}".format( strongsGreek.getName(), sk.getText(), strongsGreek.renderText( Sword.SWKey("G746") ) ) )
        except UnicodeDecodeError: print( "Unicode decode error in", strongsGreek.getName() )
        try: print( "\n{} {}: {}".format( strongsHebrew.getName(), sk.getText(), strongsHebrew.renderText( sk ) ) )
        except UnicodeDecodeError: print( "Unicode decode error in", strongsHebrew.getName() )

        if 0: # Get all vernacular booknames
            # VerseKey vk; while (!vk.Error()) { cout << vk.getBookName(); vk.setBook(vk.getBook()+1); }
            vk = Sword.VerseKey()
            while vk.popError()=='\x00':
                print( "bookname", vk.getBookName() )
                booknumber = int( bytes( vk.getBook(),'utf-8' )[0] )
                vk.setBook( booknumber + 1 )

        if 0: # Get booknames by testament (from http://www.crosswire.org/wiki/DevTools:Code_Examples)
            vk = Sword.VerseKey()
            for t in range( 1, 2+1 ):
                vk.setTestament( t )
                for i in range( 1, vk.getBookMax()+1 ):
                    vk.setBook( i )
                    print( t, i, vk.getBookName() )

        # Try a tree key on a GenBook
        module = library.getModule( 'Westminster' )
        print( "\nmodule {} ({}) {!r}".format( module.getName(), module.getType(), module.getDescription() ) )
        def getGenBookTOC( tk, parent ):
            if tk is None: # obtain one from the module
                tk = Sword.TreeKey_castTo( module.getKey() ) # Only works for gen books
            if tk and tk.firstChild():
                while True:
                    print( " ", tk.getText() )
                    # Keep track of the information for custom implementation
                    #Class *item = storeItemInfoForLaterUse(parent, text);
                    item = (parent) # temp ....................
                    if tk.hasChildren():
                        print( "  Getting children…" )
                        getGenBookTOC( tk, item )
                    if not tk.nextSibling(): break
        # end of getGenBookTOC
        getGenBookTOC( None, None )

    #Find( "sw" ) # lots!
    #Find( "store" ) # storeItemInfoForLaterUse
    #Find( "getGlobal" ) # should be lots
# end of demo

if __name__ == '__main__':
    #from multiprocessing import freeze_support
    #freeze_support() # Multiprocessing support for frozen Windows executables

    import sys
    if 'win' in sys.platform: # Convert stdout so we don't get zillions of UnicodeEncodeErrors
        from io import TextIOWrapper
        sys.stdout = TextIOWrapper( sys.stdout.detach(), sys.stdout.encoding, 'namereplace' if sys.version_info >= (3,5) else 'backslashreplace' )

    # Configure basic Bible Organisational System (BOS) set-up
    parser = BibleOrgSysGlobals.setup( ProgName, ProgVersion )
    BibleOrgSysGlobals.addStandardOptionsAndProcess( parser )

    demo()

    BibleOrgSysGlobals.closedown( ProgName, ProgVersion )
# end of SwordResources.py