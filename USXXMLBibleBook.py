#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# USXXMLBibleBook.py
#   Last modified: 2013-05-29 by RJH (also update versionString below)
#
# Module handling USX Bible Book xml
#
# Copyright (C) 2012-2013 Robert Hunt
# Author: Robert Hunt <robert316@users.sourceforge.net>
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
Module handling USX Bible book xml to produce C and Python data tables.
"""

progName = "USX XML Bible book handler"
versionString = "0.06"

import logging, os
from gettext import gettext as _
from xml.etree.ElementTree import ElementTree

import Globals
from Bible import BibleBook



class USXXMLBibleBook( BibleBook ):
    """
    Class to load, validate, and manipulate a single Bible book in USX XML.
    """
    def __init__( self, BBB ):
        """
        Create the USX Bible book object.
        """
        BibleBook.__init__( self, BBB ) # Initialise the base class
        self.objectNameString = "USX XML Bible Book object"
        self.objectTypeString = "USX"

        #self.bookReferenceCode = bookReferenceCode
    # end of USXXMLBibleBook.__init__


    def load( self, filename, folder=None, encoding='utf-8' ):
        """
        Load a single source USX XML file and extract the information.
        """

        def loadParagraph( paragraphXML, paragraphlocation ):
            """ Load a paragraph from the USX XML.
                Uses (and updates) c,v information from the containing function. """
            nonlocal c, v

            # Process the attributes first
            paragraphStyle = None
            for attrib,value in paragraphXML.items():
                if attrib=='style':
                    paragraphStyle = value # This is basically the USFM marker name
                else:
                    if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} attribute ({}) in {}").format( attrib, value, location ) )

            # Now process the paragraph text (or write a paragraph marker anyway)
            self.appendLine( paragraphStyle, paragraphXML.text if paragraphXML.text and paragraphXML.text.strip() else '' )

            # Now process the paragraph subelements
            for element in paragraphXML:
                location = element.tag + ' ' + paragraphlocation
                #print( "USXXMLBibleBook.load", c, v, element.tag, location )
                if element.tag == 'verse': # milestone (not a container)
                    Globals.checkXMLNoText( element, location )
                    Globals.checkXMLNoSubelements( element, location )
                    # Process the attributes first
                    verseStyle = None
                    for attrib,value in element.items():
                        if attrib=='number':
                            v = value
                        elif attrib=='style':
                            verseStyle = value
                        else:
                            if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} attribute ({}) in {}").format( attrib, value, location ) )
                    if verseStyle != 'v':
                        if Globals.logErrorsFlag: logging.warning( _("Unexpected style attribute ({}) in {}").format( verseStyle, location ) )
                    self.appendLine( verseStyle, v + ' ' )
                    # Now process the tail (if there's one) which is the verse text
                    if element.tail:
                        vText = element.tail
                        if vText:
                            self.appendToLastLine( vText )
                elif element.tag == 'char':
                    Globals.checkXMLNoSubelements( element, location )
                    # Process the attributes first
                    charStyle = None
                    for attrib,value in element.items():
                        if attrib=='style':
                            charStyle = value # This is basically the USFM character marker name
                            #print( "  charStyle", charStyle )
                            assert( not Globals.USFMMarkers.isNewlineMarker( charStyle ) )
                        else:
                            if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} attribute ({}) in {}").format( attrib, value, location ) )
                    # A character field must be added to the previous field
                    if element.tail is None: element.tail = ''
                    additionalText = "\\{} {}\\{}*{}".format( charStyle, element.text, charStyle, element.tail )
                    #print( c, v, paragraphStyle, charStyle )
                    self.appendToLastLine( additionalText )
                elif element.tag == 'note':
                    Globals.checkXMLNoText( element, location )
                    # Process the attributes first
                    noteStyle = noteCaller = None
                    for attrib,value in element.items():
                        if attrib=='style':
                            noteStyle = value # This is basically the USFM marker name
                            assert( noteStyle in ('x','f',) )
                        elif attrib=='caller':
                            noteCaller = value # Usually hyphen or a symbol to be used for the note
                        else:
                            if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} attribute ({}) in {}").format( attrib, value, location ) )
                    assert( noteStyle and noteCaller ) # both compulsory
                    noteLine = "\\{} {} ".format( noteStyle, noteCaller )
                    # Now process the subelements -- notes are one of the few multiply embedded fields in USX
                    for subelement in element:
                        sublocation = subelement.tag + ' ' + location
                        #print( c, v, element.tag )
                        if subelement.tag == 'char': # milestone (not a container)
                            Globals.checkXMLNoTail( subelement, sublocation )
                            Globals.checkXMLNoSubelements( subelement, sublocation )
                            # Process the attributes first
                            charStyle, charClosed = None, True
                            for attrib,value in subelement.items():
                                if attrib=='style':
                                    charStyle = value
                                elif attrib=='closed':
                                    assert( value=='false' )
                                    charClosed = False
                                else:
                                    if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} attribute ({}) in {}").format( attrib, value, sublocation ) )
                            noteLine += "\\{} {}".format( charStyle, subelement.text )
                            if charClosed: noteLine += "\\{}*".format( charStyle )
                        else:
                            if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} subelement after {} {}:{} in {}").format( subelement.tag, self.bookReferenceCode, c, v, sublocation ) )
                            self.addPriorityError( 1, c, v, _("Unprocessed {} subelement").format( subelement.tag ) )
                    if subelement.tail and subelement.tail.strip(): noteLine += subelement.tail
                    #noteLine += "\\{}*".format( charStyle )
                    noteLine += "\\{}*".format( noteStyle )
                    if element.tail: noteLine += element.tail
                    self.appendToLastLine( noteLine )
                elif element.tag == 'unmatched': # Used to denote errors in the source text
                    Globals.checkXMLNoText( element, location )
                    Globals.checkXMLNoTail( element, location )
                    Globals.checkXMLNoAttributes( element, location )
                    Globals.checkXMLNoSubelements( element, location )
                else:
                    if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} element after {} {}:{} in {}").format( element.tag, self.bookReferenceCode, c, v, location ) )
                    self.addPriorityError( 1, c, v, _("Unprocessed {} element").format( element.tag ) )
                    for x in range(max(0,len(self)-10),len(self)): print( x, self._rawLines[x] )
                    if Globals.debugFlag: halt
        # end of loadParagraph

        if Globals.verbosityLevel > 2: print( "  " + _("Loading {}...").format( filename ) )
        self.isOneChapterBook = self.bookReferenceCode in Globals.BibleBooksCodes.getSingleChapterBooksList()
        self.sourceFilename = filename
        self.sourceFolder = folder
        self.sourceFilepath = os.path.join( folder, filename ) if folder else filename
        self.tree = ElementTree().parse( self.sourceFilepath )
        assert( len ( self.tree ) ) # Fail here if we didn't load anything at all

        c = v = '0'
        loadErrors = []

        # Find the main container
        if self.tree.tag=='usx' or self.tree.tag=='usfm': # Not sure why both are allowable
            location = "USX ({}) file".format( self.tree.tag )
            Globals.checkXMLNoText( self.tree, location )
            Globals.checkXMLNoTail( self.tree, location )

            # Process the attributes first
            self.schemaLocation = ''
            version = None
            for attrib,value in self.tree.items():
                if attrib=='version': version = value
                elif Globals.logErrorsFlag: logging.warning( _("Unprocessed {} attribute ({}) in {}").format( attrib, value, location ) )
            if version not in ( None, '2.0' ):
                if Globals.logErrorsFlag: logging.warning( _("Not sure if we can handle v{} USX files").format( version ) )

            # Now process the data
            for element in self.tree:
                sublocation = element.tag + " " + location
                if element.tag == 'book': # milestone (not a container)
                    Globals.checkXMLNoSubelements( element, sublocation )
                    Globals.checkXMLNoTail( element, sublocation )
                    # Process the attributes
                    idField = bookStyle = None
                    for attrib,value in element.items():
                        if attrib=='id' or attrib=='code':
                            idField = value # Should be USFM bookcode (not like bookReferenceCode which is BibleOrgSys BBB bookcode)
                            #if idField != bookReferenceCode:
                            #    if Globals.logErrorsFlag: logging.warning( _("Unexpected book code ({}) in {}").format( idField, sublocation ) )
                        elif attrib=='style':
                            bookStyle = value
                        else:
                            if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} attribute ({}) in {}").format( attrib, value, sublocation ) )
                    if bookStyle != 'id':
                        if Globals.logErrorsFlag: logging.warning( _("Unexpected style attribute ({}) in {}").format( bookStyle, sublocation ) )
                    idLine = idField
                    if element.text and element.text.strip(): idLine += ' ' + element.text
                    self.appendLine( 'id', idLine )
                elif element.tag == 'chapter': # milestone (not a container)
                    v = '0'
                    Globals.checkXMLNoText( element, sublocation )
                    Globals.checkXMLNoTail( element, sublocation )
                    Globals.checkXMLNoSubelements( element, sublocation )
                    # Process the attributes
                    chapterStyle = None
                    for attrib,value in element.items():
                        if attrib=='number':
                            c = value
                        elif attrib=='style':
                            chapterStyle = value
                        else:
                            if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} attribute ({}) in {}").format( attrib, value, sublocation ) )
                    if chapterStyle != 'c':
                        if Globals.logErrorsFlag: logging.warning( _("Unexpected style attribute ({}) in {}").format( chapterStyle, sublocation ) )
                    self.appendLine( 'c', c )
                elif element.tag == 'para':
                    Globals.checkXMLNoTail( element, sublocation )
                    USFMMarker = element.attrib['style'] # Get the USFM code for the paragraph style
                    if Globals.USFMMarkers.isNewlineMarker( USFMMarker ):
                        #if lastMarker: self.appendLine( lastMarker, lastText )
                        #lastMarker, lastText = USFMMarker, text
                        loadParagraph( element, sublocation )
                    elif Globals.USFMMarkers.isInternalMarker( USFMMarker ): # the line begins with an internal USFM Marker -- append it to the previous line
                        text = element.text
                        if text is None: text = ''
                        if Globals.debugFlag:
                            print( _("{} {}:{} Found '\\{}' internal USFM marker at beginning of line with text: {}").format( self.bookReferenceCode, c, v, USFMMarker, text ) )
                            #halt # Not checked yet
                        if text:
                            loadErrors.append( _("{} {}:{} Found '\\{}' internal USFM marker at beginning of line with text: {}").format( self.bookReferenceCode, c, v, USFMMarker, text ) )
                            if Globals.logErrorsFlag: logging.warning( _("Found '\\{}' internal USFM Marker after {} {}:{} at beginning of line with text: {}").format( USFMMarker, self.bookReferenceCode, c, v, text ) )
                        else: # no text
                            loadErrors.append( _("{} {}:{} Found '\\{}' internal USFM Marker at beginning of line (with no text)").format( self.bookReferenceCode, c, v, USFMMarker ) )
                            if Globals.logErrorsFlag: logging.warning( _("Found '\\{}' internal USFM Marker after {} {}:{} at beginning of line (with no text)").format( USFMMarker, self.bookReferenceCode, c, v ) )
                        self.addPriorityError( 97, c, v, _("Found \\{} internal USFM Marker on new line in file").format( USFMMarker ) )
                        #lastText += '' if lastText.endswith(' ') else ' ' # Not always good to add a space, but it's their fault!
                        lastText =  '\\' + USFMMarker + ' ' + text
                        #print( "{} {} {} Now have {}:'{}'".format( self.bookReferenceCode, c, v, lastMarker, lastText ) )
                    else: # the line begins with an unknown USFM Marker
                        text = element.text
                        if text:
                            loadErrors.append( _("{} {}:{} Found '\\{}' unknown USFM Marker at beginning of line with text: {}").format( self.bookReferenceCode, c, v, USFMMarker, text ) )
                            if Globals.logErrorsFlag: logging.error( _("Found '\\{}' unknown USFM Marker after {} {}:{} at beginning of line with text: {}").format( USFMMarker, self.bookReferenceCode, c, v, text ) )
                        else: # no text
                            loadErrors.append( _("{} {}:{} Found '\\{}' unknown USFM Marker at beginning of line (with no text").format( self.bookReferenceCode, c, v, USFMMarker ) )
                            if Globals.logErrorsFlag: logging.error( _("Found '\\{}' unknown USFM Marker after {} {}:{} at beginning of line (with no text)").format( USFMMarker, self.bookReferenceCode, c, v ) )
                        self.addPriorityError( 100, c, v, _("Found \\{} unknown USFM Marker on new line in file").format( USFMMarker ) )
                        for tryMarker in sorted( Globals.USFMMarkers.getNewlineMarkersList(), key=len, reverse=True ): # Try to do something intelligent here -- it might be just a missing space
                            if USFMMarker.startswith( tryMarker ): # Let's try changing it
                                if lastMarker: self.appendLine( lastMarker, lastText )
                                lastMarker, lastText = tryMarker, USFMMarker[len(tryMarker):] + ' ' + text
                                loadErrors.append( _("{} {}:{} Changed '\\{}' unknown USFM Marker to '{}' at beginning of line: {}").format( self.bookReferenceCode, c, v, USFMMarker, tryMarker, text ) )
                                if Globals.logErrorsFlag: logging.warning( _("Changed '\\{}' unknown USFM Marker to '{}' after {} {}:{} at beginning of line: {}").format( USFMMarker, tryMarker, self.bookReferenceCode, c, v, text ) )
                                break
                        # Otherwise, don't bother processing this line -- it'll just cause more problems later on
                else:
                    if Globals.logErrorsFlag: logging.warning( _("Unprocessed {} element after {} {}:{} in {}").format( element.tag, self.bookReferenceCode, c, v, sublocation ) )
                    self.addPriorityError( 1, c, v, _("Unprocessed {} element").format( element.tag ) )

        if loadErrors: self.errorDictionary['Load Errors'] = loadErrors
    # end of USXXMLBibleBook.load
# end of class USXXMLBibleBook



def demo():
    """
    Main program to handle command line parameters and then run what they want.
    """
    if Globals.verbosityLevel > 0: print( "{} V{}".format( progName, versionString ) )

    def getShortVersion( someString ):
        maxLen = 140
        if len(someString)<maxLen: return someString
        return someString[:int(maxLen/2)]+'...'+someString[-int(maxLen/2):]

    import USXFilenames, USFMFilenames, USFMBibleBook
    #name, testFolder = "Matigsalug", "../../../../../Data/Work/VirtualBox_Shared_Folder/PT7.3 Exports/USXExports/Projects/MBTV/" # You can put your USX test folder here
    name, testFolder = "Matigsalug", "../../../../../Data/Work/VirtualBox_Shared_Folder/PT7.4 Exports/USX Exports/MBTV/" # You can put your USX test folder here
    name2, testFolder2 = "Matigsalug", "../../../../../Data/Work/Matigsalug/Bible/MBTV/" # You can put your USFM test folder here (for comparing the USX with)
    if os.access( testFolder, os.R_OK ):
        if Globals.verbosityLevel > 1: print( _("Scanning {} from {}...").format( name, testFolder ) )
        if Globals.verbosityLevel > 1: print( _("Scanning {} from {}...").format( name, testFolder2 ) )
        fileList = USXFilenames.USXFilenames( testFolder ).getConfirmedFilenames()
        for bookReferenceCode,filename in fileList:
            if bookReferenceCode in (
                     'GEN',
                    'RUT', 'EST',
                    'DAN', 'JNA',
                    'MAT','MRK','LUK','JHN','ACT',
                    'ROM','CO1','CO2','GAL','EPH','PHP','COL','TH1','TH2','TI1','TI2','TIT','PHM',
                    'HEB','JAM','PE1','PE2','JN1','JN2','JN3','JDE','REV'
                    ):
                if Globals.verbosityLevel > 1: print( _("Loading {} from {}...").format( bookReferenceCode, filename ) )
                UxBB = USXXMLBibleBook( bookReferenceCode )
                UxBB.load( filename, testFolder )
                if Globals.verbosityLevel > 2: print( "  ID is '{}'".format( UxBB.getField( 'id' ) ) )
                if Globals.verbosityLevel > 2: print( "  Header is '{}'".format( UxBB.getField( 'h' ) ) )
                if Globals.verbosityLevel > 2: print( "  Main titles are '{}' and '{}'".format( UxBB.getField( 'mt1' ), UxBB.getField( 'mt2' ) ) )
                if Globals.verbosityLevel > 2: print( UxBB )
                UxBB.validateUSFM()
                UxBBVersification = UxBB.getVersification ()
                if Globals.verbosityLevel > 2: print( UxBBVersification )
                UxBBAddedUnits = UxBB.getAddedUnits ()
                if Globals.verbosityLevel > 2: print( UxBBAddedUnits )
                UxBB.check()
                UxBBErrors = UxBB.getErrors()
                if Globals.verbosityLevel > 2: print( UxBBErrors )

                # Test our USX code by comparing with the original USFM books
                if os.access( testFolder2, os.R_OK ):
                    fileList2 = USFMFilenames.USFMFilenames( testFolder2 ).getConfirmedFilenameTuples()
                    found2 = False
                    for bookReferenceCode2,filename2 in fileList2:
                        if bookReferenceCode2 == bookReferenceCode:
                            found2 = True; break
                    if found2:
                        if Globals.verbosityLevel > 2: print( _("Loading {} from {}...").format( bookReferenceCode2, filename2 ) )
                        UBB = USFMBibleBook.USFMBibleBook( bookReferenceCode )
                        UBB.load( filename2, testFolder2 )
                        #print( "  ID is '{}'".format( UBB.getField( 'id' ) ) )
                        #print( "  Header is '{}'".format( UBB.getField( 'h' ) ) )
                        #print( "  Main titles are '{}' and '{}'".format( UBB.getField( 'mt1' ), UBB.getField( 'mt2' ) ) )
                        if Globals.verbosityLevel > 2: print( UBB )
                        UBB.validateUSFM()

                        # Now compare the USX and USFM projects
                        if 0:
                            print( "\nPRINTING COMPARISON" )
                            ixFrom, ixTo = 8, 40
                            if ixTo-ixFrom < 10:
                                print( "UsxBB[{}-{}]".format( ixFrom, ixTo ) )
                                for ix in range( ixFrom, ixTo ): print( "  {} {}".format( 'GUD' if UxBB._processedLines[ix]==UBB._processedLines[ix] else 'BAD', UxBB._processedLines[ix] ) )
                                print( "UsfBB[{}-{}]".format( ixFrom, ixTo ) )
                                for ix in range( ixFrom, ixTo ): print( "  {} {}".format( 'GUD' if UxBB._processedLines[ix]==UBB._processedLines[ix] else 'BAD', UBB._processedLines[ix] ) )
                            else:
                                for ix in range( ixFrom, ixTo ):
                                    print( "UsxBB[{}]: {} {}".format( ix, 'GUD' if UxBB._processedLines[ix]==UBB._processedLines[ix] else 'BAD', UxBB._processedLines[ix] ) )
                                    print( "UsfBB[{}]: {} {}".format( ix, 'GUD' if UxBB._processedLines[ix]==UBB._processedLines[ix] else 'BAD', UBB._processedLines[ix] ) )
                            print( "END COMPARISON\n" )

                        mismatchCount = 0
                        UxL, UL = len(UxBB), len(UBB)
                        for i in range(0, max( UxL, UL ) ):
                            if i<UxL and i<UL:
                                if UxBB._processedLines[i] != UBB._processedLines[i]:
                                    #print( "usx ", i, len(UxBB._processedLines[i]), str(UxBB._processedLines[i])[:2] )
                                    #print( "usfm", i, len(UBB._processedLines[i]), UBB._processedLines[i][0]) #[:2] )
                                    print( "\n{} line {} not equal: {}({}) from {}({})".format( bookReferenceCode, i, UxBB._processedLines[i][0], UxBB._processedLines[i][1], UBB._processedLines[i][0], UBB._processedLines[i][1] ) )
                                    if UxBB._processedLines[i][2] != UBB._processedLines[i][2]:
                                        print( "   UsxBB[2]: '{}'".format( getShortVersion( UxBB._processedLines[i][2] ) ) )
                                        print( "   UsfBB[2]: '{}'".format( getShortVersion( UBB._processedLines[i][2] ) ) )
                                    if (UxBB._processedLines[i][3] or UBB._processedLines[i][3]) and UxBB._processedLines[i][3]!=UBB._processedLines[i][3]:
                                        print( "   UdsBB[3]: '{}'".format( getShortVersion( UxBB._processedLines[i][3] ) ) )
                                        print( "   UsfBB[3]: '{}'".format( getShortVersion( UBB._processedLines[i][3] ) ) )
                                    mismatchCount += 1
                            else: # one has more lines
                                print( "Linecount not equal: {} from {}".format( i, UxL, UL ) )
                                mismatchCount += 1
                                break
                            if mismatchCount > 5: print( "..." ); break
                        if mismatchCount == 0 and Globals.verbosityLevel > 2: print( "All {} processedLines matched!".format( UxL ) )
                    else: print( "Sorry, USFM test folder doesn't contain the {} book.".format( bookReferenceCode ) )
                else: print( "Sorry, USFM test folder '{}' doesn't exist on this computer.".format( testFolder2 ) )
            elif Globals.verbosityLevel > 2: print( "*** Skipped USX/USFM compare on {}", bookReferenceCode )
    else: print( "Sorry, USX test folder '{}' doesn't exist on this computer.".format( testFolder ) )
# end of demo

if __name__ == '__main__':
    # Configure basic logging
    logging.basicConfig( format='%(levelname)s: %(message)s', level=logging.INFO ) # Removes the unnecessary and unhelpful 'root:' part of the logged messages

    # Handle command line parameters
    from optparse import OptionParser
    parser = OptionParser( version="v{}".format( versionString ) )
    #parser.add_option("-e", "--export", action="store_true", dest="export", default=False, help="export the XML file to .py and .h tables suitable for directly including into other programs")
    Globals.addStandardOptionsAndProcess( parser )

    demo()
# end of USXXMLBibleBook.py