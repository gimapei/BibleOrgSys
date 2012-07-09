#!/usr/bin/python3
#
# InternalBible.py
#   Last modified: 2012-07-10 by RJH (also update versionString below)
#
# Module handling the USFM markers for Bible books
#
# Copyright (C) 2010-2012 Robert Hunt
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
Module for defining and manipulating Bibles in our internal USFM-based 'lines' format.

The calling class needs to call this base class __init__ routine and also set:
    self.objectType (with "USFM" or "USX")
    self.objectNameString (with a description of the type of Bible object)
It also needs to provide a "load" routine that sets:
    self.sourceFolder
and then fills
    self.books
"""

progName = "Internal Bible handler"
versionString = "0.04"


import os, logging, datetime
from gettext import gettext as _
from collections import OrderedDict

import Globals, ControlFiles
from BibleBooksCodes import BibleBooksCodes
from USFMMarkers import USFMMarkers


class InternalBible:
    """
    Class to load and manipulate InternalBibles.

    """
    def __init__( self, name, logErrorsFlag ):
        """
        Create the object.
        """
        self.name = name
        self.logErrorsFlag = logErrorsFlag

        # Set up empty containers for the object
        self.books = OrderedDict()
        self.ssfPathName, self.ssfData = '', {}
        self.BBBToNameDict, self.bookNameDict, self.combinedBookNameDict, self.bookAbbrevDict = {}, {}, {}, {} # Used to store book name and abbreviations (pointing to the BBB codes)
        self.reverseDict, self.guesses = {}, '' # A program history

        # Set up filled containers for the object
        self.BibleBooksCodes = BibleBooksCodes().loadData()
        self.OneChapterBBBBookCodes = self.BibleBooksCodes.getSingleChapterBooksList()
        self.USFMMarkers = USFMMarkers().loadData()
    # end of __init_


    def __str__( self ):
        """
        This method returns the string representation of a Bible.
        
        @return: the name of a Bible object formatted as a string
        @rtype: string
        """
        result = self.objectNameString
        if self.name: result += ('\n' if result else '') + "  Name: " + self.name
        if self.sourceFolder: result += ('\n' if result else '') + "  From: " + self.sourceFolder
        result += ('\n' if result else '') + "  Number of books = " + str(len(self.books))
        return result
    # end of __str__


    def getAssumedBookName( self, BBB ):
        """Gets the book name for the given book reference code."""
        assert( BBB in self.BibleBooksCodes)
        #assert( self.books[BBB] )
        if BBB in self.BBBToNameDict: return self.BBBToNameDict[BBB]
    # end of getAssumedBookName


    def guessXRefBBB( self, referenceString ):
        """ Attempt to return a book reference code given a book reference code (e.g., 'PRO'), a book name (e.g., Proverbs) or abbreviation (e.g., Prv).
            Uses self.combinedBookNameDict and makes and uses self.bookAbbrevDict.
            Return None if unsuccessful."""
        result = self.BibleBooksCodes.getBBB( referenceString )
        if result is not None: return result # It's already a valid BBB

        adjRefString = referenceString.lower()
        if adjRefString in self.combinedBookNameDict:
            BBB = self.combinedBookNameDict[adjRefString]
            #assert( BBB not in self.reverseDict )
            self.reverseDict[BBB] = referenceString
            return BBB # Found a whole name match
        if adjRefString in self.bookAbbrevDict:
            BBB = self.bookAbbrevDict[adjRefString]
            #print( referenceString, adjRefString, BBB, self.reverseDict )
            #assert( BBB not in self.reverseDict )
            self.reverseDict[BBB] = referenceString
            return BBB # Found a whole abbreviation match

        # Do a program check
        for BBB in self.reverseDict: assert( self.reverseDict[BBB] != referenceString )

        # See if a book name starts with this string
        if Globals.debugFlag: print( "  getXRefBBB using startswith1..." )
        count = 0
        for bookName in self.bookNameDict:
            if bookName.startswith( adjRefString ):
                BBB = self.bookNameDict[bookName]
                count += 1
        if count == 1: # Found exactly one
            self.bookAbbrevDict[adjRefString] = BBB # Save to make it faster next time
            self.guesses += ('\n' if self.guesses else '') + "Guessed '{}' to be {} (startswith1)".format( referenceString, BBB )
            self.reverseDict[BBB] = referenceString
            return BBB
        elif count == 2: # Found exactly two but one of them might have a different abbreviation that we already know
            secondCount = 0
            for bookName in self.bookNameDict: # Gotta go through them all again now :(
                if bookName.startswith( adjRefString ):
                    BBBx = self.bookNameDict[bookName]
                    if BBBx not in self.reverseDict: BBB = BBBx; secondCount += 1
            if secondCount == 1: # Found exactly one
                self.bookAbbrevDict[adjRefString] = BBB # Save to make it faster next time
                self.guesses += ('\n' if self.guesses else '') + "Guessed '{}' to be {} (startswith1SECOND)".format( referenceString, BBB )
                self.reverseDict[BBB] = referenceString
                return BBB
        if Globals.debugFlag and count > 1: print( "  getXRefBBB has multiple startswith matches for '{}' in {}".format( adjRefString, self.combinedBookNameDict ) )
        if count == 0:
            if Globals.debugFlag: print( "  getXRefBBB using startswith2..." )
            for bookName in self.combinedBookNameDict:
                if bookName.startswith( adjRefString ):
                    BBB = self.combinedBookNameDict[bookName]
                    count += 1
            if count == 1: # Found exactly one now
                self.bookAbbrevDict[adjRefString] = BBB # Save to make it faster next time
                self.guesses += ('\n' if self.guesses else '') + "Guessed '{}' to be {} (startswith2)".format( referenceString, BBB )
                self.reverseDict[BBB] = referenceString
                return BBB
        elif count == 2: # Found exactly two but one of them might have a different abbreviation that we already know
            secondCount = 0
            for bookName in self.bookNameDict: # Gotta go through them all again now :(
                if bookName.startswith( adjRefString ):
                    BBBx = self.bookNameDict[bookName]
                    if BBBx not in self.reverseDict: BBB = BBBx; secondCount += 1
            if secondCount == 1: # Found exactly one now
                self.bookAbbrevDict[adjRefString] = BBB # Save to make it faster next time
                self.guesses += ('\n' if self.guesses else '') + "Guessed '{}' to be {} (startswith2SECOND)".format( referenceString, BBB )
                self.reverseDict[BBB] = referenceString
                return BBB

        # See if a book name contains a word that starts with this string
        if count == 0:
            if Globals.debugFlag: print( "  getXRefBBB using word startswith..." )
            for bookName in self.bookNameDict:
                if ' ' in bookName:
                    for bit in bookName.split():
                        if bit.startswith( adjRefString ):
                            BBB = self.bookNameDict[bookName]
                            count += 1
            if count == 1: # Found exactly one
                self.bookAbbrevDict[adjRefString] = BBB # Save to make it faster next time
                self.guesses += ('\n' if self.guesses else '') + "Guessed '{}' to be {} (word startswith)".format( referenceString, BBB )
                self.reverseDict[BBB] = referenceString
                return BBB
            if Globals.debugFlag and count > 1: print( "  getXRefBBB has multiple startswith matches for '{}' in {}".format( adjRefString, self.bookNameDict ) )

        # See if a book name starts with the same letter plus contains the letters in this string (slow)
        if count == 0:
            if Globals.debugFlag: print ("  getXRefBBB using first plus other characters..." )
            for bookName in self.bookNameDict:
                if not bookName: print( self.bookNameDict ); halt # temp...
                #print( "aRS='{}', bN='{}'".format( adjRefString, bookName ) )
                if adjRefString[0] != bookName[0]: continue # The first letters don't match
                found = True
                for char in adjRefString[1:]:
                    if char not in bookName[1:]: # We could also check that they're in the correct order........................might give less ambiguities???
                        found = False
                        break
                if not found: continue
                #print( "  getXRefBBB: p...", bookName )
                BBB = self.bookNameDict[bookName]
                count += 1
            if count == 1: # Found exactly one
                self.bookAbbrevDict[adjRefString] = BBB # Save to make it faster next time
                self.guesses += ('\n' if self.guesses else '') + "Guessed '{}' to be {} (firstletter+)".format( referenceString, BBB )
                return BBB
            if Globals.debugFlag and count > 1: print( "  getXRefBBB has first and other character multiple matches for '{}' in {}".format( adjRefString, self.bookNameDict ) )

        if 0: # Too error prone!!!
            # See if a book name contains the letters in this string (slow)
            if count == 0:
                if Globals.debugFlag: print ("  getXRefBBB using characters..." )
                for bookName in self.bookNameDict:
                    found = True
                    for char in adjRefString:
                        if char not in bookName: # We could also check that they're in the correct order........................might give less ambiguities???
                            found = False
                            break
                    if not found: continue
                    #print( "  getXRefBBB: q...", bookName )
                    BBB = self.bookNameDict[bookName]
                    count += 1
                if count == 1: # Found exactly one
                    self.bookAbbrevDict[adjRefString] = BBB # Save to make it faster next time
                    self.guesses += ('\n' if self.guesses else '') + "Guessed '{}' to be {} (letters)".format( referenceString, BBB )
                    return BBB
                if Globals.debugFlag and count > 1: print( "  getXRefBBB has character multiple matches for '{}' in {}".format( adjRefString, self.bookNameDict ) )

        if Globals.debugFlag or Globals.verbosityLevel>2: print( "  getXRefBBB failed for '{}' with {} and {}".format( referenceString, self.bookNameDict, self.bookAbbrevDict ) )
        string = "Couldn't guess '{}'".format( referenceString[:5] )
        if string not in self.guesses: self.guesses += ('\n' if self.guesses else '') + string
    # end of guessXRefBBB


    def getVersification( self ):
        """
        Get the versification of the Bible into four ordered dictionaries with the referenceAbbreviation as key.
            Entries in both are lists of tuples, being (c, v).
            The first list contains an entry for each chapter in the book showing the number of verses.
            The second list contains an entry for each missing verse in the book (not including verses that are missing at the END of a chapter).
            The third list contains an entry for combined verses in the book.
            The fourth list contains an entry for reordered verses in the book.
        """
        assert( self.books )
        totalVersification, totalOmittedVerses, totalCombinedVerses, totalReorderedVerses = OrderedDict(), OrderedDict(), OrderedDict(), OrderedDict()
        for bookReferenceCode in self.books.keys():
            versification, omittedVerses, combinedVerses, reorderedVerses = self.books[bookReferenceCode].getVersification()
            totalVersification[bookReferenceCode] = versification
            if omittedVerses: totalOmittedVerses[bookReferenceCode] = omittedVerses # Only add an entry if there are some
            if combinedVerses: totalCombinedVerses[bookReferenceCode] = combinedVerses
            if reorderedVerses: totalReorderedVerses[bookReferenceCode] = reorderedVerses
        return totalVersification, totalOmittedVerses, totalCombinedVerses, totalReorderedVerses
    # end of getVersification


    def getAddedUnits( self ):
        """
        Get the added units in the Bible text, such as section headings, paragraph breaks, and section references.
        """
        assert( self.books )
        haveParagraphs = haveQParagraphs = haveSectionHeadings = haveSectionReferences = False
        AllParagraphs, AllQParagraphs, AllSectionHeadings, AllSectionReferences = OrderedDict(), OrderedDict(), OrderedDict(), OrderedDict()
        for BBB in self.books:
            paragraphReferences, qReferences, sectionHeadings, sectionReferences = self.books[BBB].getAddedUnits()
            if paragraphReferences: haveParagraphs = True
            AllParagraphs[BBB] = paragraphReferences # Add an entry for each given book, even if the entry is blank
            if qReferences: haveQParagraphs = True
            AllQParagraphs[BBB] = qReferences
            if sectionHeadings: haveSectionHeadings = True
            AllSectionHeadings[BBB] = sectionHeadings
            if sectionReferences: haveSectionReferences = True
            AllSectionReferences[BBB] = sectionReferences
        # If a version lacks a feature completely, return None (rather than an empty dictionary)
        return AllParagraphs if haveParagraphs else None, AllQParagraphs if haveQParagraphs else None, AllSectionHeadings if haveSectionHeadings else None, AllSectionReferences if haveSectionReferences else None
    # end of getAddedUnits


    def check( self ):
        """Runs a series of individual checks (and counts) on each book of the Bible
            and then a number of overall checks on the entire Bible."""
        # Get our recommendations for added units -- only load this once per Bible
        import pickle
        folder = os.path.join( os.path.dirname(__file__), "DataFiles/", "ScrapedFiles/" ) # Relative to module, not cwd
        filepath = os.path.join( folder, "AddedUnitData.pickle" )
        if Globals.verbosityLevel > 3: print( _("Importing from {}...").format( filepath ) )
        with open( filepath, 'rb' ) as pickleFile:
            typicalAddedUnits = pickle.load( pickleFile ) # The protocol version used is detected automatically, so we do not have to specify it

        if Globals.verbosityLevel > 2: print( _("Running checks on {}...").format( self.name ) )
        for BBB in self.books: # Do individual book checks
            if Globals.verbosityLevel > 3: print( "  " + _("Checking {}...").format( BBB ) )
            self.books[BBB].check( typicalAddedUnits )

        # Do overall Bible checks
        # xxxxxxxxxxxxxxxxx ......................................
    # end of check


    def getErrors( self ):
        """Returns the error dictionary.
            All keys ending in 'Errors' give lists of strings.
            All keys ending in 'Counts' give OrderedDicts with [value]:count entries
            All other keys give subkeys
            The structure is:
                errors: OrderedDict
                    ['ByBook']: OrderedDict
                        ['All Books']: OrderedDict
                        [BBB] in order: OrderedDict
                            ['Priority Errors']: list
                            ['Load Errors']: list
                            ['Fix Text Errors']: list
                            ['Versification Errors']: list
                            ['SFMs']: OrderedDict
                                ['Newline Marker Errors']: list
                                ['Internal Marker Errors']: list
                                ['All Newline Marker Counts']: OrderedDict
                            ['Characters']: OrderedDict
                                ['All Character Counts']: OrderedDict
                                ['Letter Counts']: OrderedDict
                                ['Punctuation Counts']: OrderedDict
                            ['Words']: OrderedDict
                                ['All Word Counts']: OrderedDict
                                ['Case Insensitive Word Counts']: OrderedDict
                            ['Headings']: OrderedDict
                    ['ByCategory']: OrderedDict
        """
        def appendList( BBB, errorDict, firstKey, secondKey=None ):
            """Appends a list to the ALL BOOKS errors."""
            #print( "  appendList", BBB, firstKey, secondKey )
            if secondKey is None:
                assert( isinstance (errorDict[BBB][firstKey], list ) )
                if firstKey not in errorDict['All Books']: errorDict['All Books'][firstKey] = []
                errorDict['All Books'][firstKey].extend( errorDict[BBB][firstKey] )
            else: # We have an extra level
                assert( isinstance (errorDict[BBB][firstKey], dict ) )
                assert( isinstance (errorDict[BBB][firstKey][secondKey], list ) )
                if firstKey not in errorDict['All Books']: errorDict['All Books'][firstKey] = OrderedDict()
                if secondKey not in errorDict['All Books'][firstKey]: errorDict['All Books'][firstKey][secondKey] = []
                errorDict['All Books'][firstKey][secondKey].extend( errorDict[BBB][firstKey][secondKey] )
        # end of appendList

        def mergeCount( BBB, errorDict, firstKey, secondKey=None ):
            """Merges the counts together."""
            #print( "  mergeCount", BBB, firstKey, secondKey )
            if secondKey is None:
                assert( isinstance (errorDict[BBB][firstKey], dict ) )
                if firstKey not in errorDict['All Books']: errorDict['All Books'][firstKey] = {}
                for something in errorDict[BBB][firstKey]:
                    errorDict['All Books'][firstKey][something] = 1 if something not in errorDict['All Books'][firstKey] else errorDict[BBB][firstKey][something] + 1
            else:
                assert( isinstance (errorDict[BBB][firstKey], (dict, OrderedDict,) ) )
                assert( isinstance (errorDict[BBB][firstKey][secondKey], dict ) )
                if firstKey not in errorDict['All Books']: errorDict['All Books'][firstKey] = OrderedDict()
                if secondKey not in errorDict['All Books'][firstKey]: errorDict['All Books'][firstKey][secondKey] = {}
                for something in errorDict[BBB][firstKey][secondKey]:
                    errorDict['All Books'][firstKey][secondKey][something] = errorDict[BBB][firstKey][secondKey][something] if something not in errorDict['All Books'][firstKey][secondKey] \
                                                                                else errorDict['All Books'][firstKey][secondKey][something] + errorDict[BBB][firstKey][secondKey][something]
        # end of mergeCount

        def getCapsList( lcWord, lcTotal, wordDict ):
            """ Given that a lower case word has a lowercase count of lcTotal,
                search wordDict to find all the ways that it occurs
                and return this as a list sorted with the most frequent first."""
            tempResult = []

            lcCount = wordDict[lcWord] if lcWord in wordDict else 0
            if lcCount: tempResult.append( (lcCount,lcWord,) )
            total = lcCount

            if total < lcTotal:
                tcWord = lcWord.title() # NOTE: This can make in-enew into In-Enew
                assert( tcWord != lcWord )
                tcCount = wordDict[tcWord] if tcWord in wordDict else 0
                if tcCount: tempResult.append( (tcCount,tcWord,) ); total += tcCount
            if total < lcTotal:
                TcWord = lcWord[0].upper() + lcWord[1:] # NOTE: This can make in-enew into In-enew
                #print( lcWord, tcWord, TcWord )
                #assert( TcWord != lcWord )
                if TcWord!=lcWord and TcWord!=tcWord: # The first two can be equal if the first char is non-alphabetic
                    TcCount = wordDict[TcWord] if TcWord in wordDict else 0
                    if TcCount: tempResult.append( (TcCount,TcWord,) ); total += TcCount
            if total < lcTotal:
                tCWord = tcWord[0].lower() + tcWord[1:] # NOTE: This can make Matig-Kurintu into matig-Kurintu (but won't change 1Cor)
                if tCWord!=lcWord and tCWord!=tcWord and tCWord!=TcWord:
                    tCCount = wordDict[tCWord] if tCWord in wordDict else 0
                    if tCCount: tempResult.append( (tCCount,tCWord,) ); total += tCCount
            if total < lcTotal:
                UCWord = lcWord.upper()
                assert( UCWord!=lcWord )
                if UCWord != TcWord:
                    UCCount = wordDict[UCWord] if UCWord in wordDict else 0
                    if UCCount: tempResult.append( (UCCount,UCWord,) ); total += UCCount
            if total < lcTotal: # There's only one (slow) way left -- look at every word
                for word in wordDict:
                    if word.lower()==lcWord and word not in ( lcWord, tcWord, TcWord, tCWord, UCWord ):
                        tempResult.append( (wordDict[word],word,) ); total += wordDict[word]
                        if 'Possible Word Errors' not in errors['ByBook']['All Books']['Words']: errors['ByBook']['All Books']['Words']['Possible Word Errors'] = []
                        errors['ByBook']['All Books']['Words']['Possible Word Errors'].append( _("Word '{}' appears to have unusual capitalization").format( word ) )
                        if total == lcTotal: break # no more to find

            if total < lcTotal:
                print( "Couldn't get word total with", lcWord, lcTotal, total, tempResult )
                print( lcWord, tcWord, TcWord, tCWord, UCWord )

            result = [w for c,w in sorted(tempResult)]
            #if len(tempResult)>2: print( lcWord, lcTotal, total, tempResult, result )
            return result
        # end of getCapsList

        # Set up
        errors = OrderedDict(); errors['ByBook'] = OrderedDict(); errors['ByCategory'] = OrderedDict()
        for category in ('Priority Errors','Load Errors','Fix Text Errors','Validation Errors','Versification Errors',):
            errors['ByCategory'][category] = [] # get these in a logical order (remember: they might not all occur for each book)
        for category in ('SFMs','Characters','Words','Headings','Introduction','Notes',): # get these in a logical order
            errors['ByCategory'][category] = OrderedDict()
        errors['ByBook']['All Books'] = OrderedDict()

        # Make sure that the error lists come first in the All Books ordered dictionaries (even if there's no errors for the first book)
        for BBB in self.books.keys():
            errors['ByBook'][BBB] = self.books[BBB].getErrors()
            for thisKey in errors['ByBook'][BBB]:
                if thisKey.endswith('Errors'):
                    errors['ByBook']['All Books'][thisKey] = []
                    errors['ByCategory'][thisKey] = []
                elif not thisKey.endswith('List') and not thisKey.endswith('Lines'):
                    for anotherKey in errors['ByBook'][BBB][thisKey]:
                        if anotherKey.endswith('Errors'):
                            if thisKey not in errors['ByBook']['All Books']: errors['ByBook']['All Books'][thisKey] = OrderedDict()
                            errors['ByBook']['All Books'][thisKey][anotherKey] = []
                            if thisKey not in errors['ByCategory']: errors['ByCategory'][thisKey] = OrderedDict()
                            errors['ByCategory'][thisKey][anotherKey] = []

        # Combine book errors into Bible totals plus into categories
        for BBB in self.books.keys():
            #errors['ByBook'][BBB] = self.books[BBB].getErrors()

            # Correlate some of the totals (i.e., combine book totals into Bible totals)
            # Also, create a dictionary of errors by category (as well as the main one by book reference code BBB)
            for thisKey in errors['ByBook'][BBB]:
                #print( "thisKey", BBB, thisKey )
                if thisKey.endswith('Errors') or thisKey.endswith('List') or thisKey.endswith('Lines'):
                    assert( isinstance( errors['ByBook'][BBB][thisKey], list ) )
                    appendList( BBB, errors['ByBook'], thisKey )
                    errors['ByCategory'][thisKey].extend( errors['ByBook'][BBB][thisKey] )
                elif thisKey.endswith('Counts'):
                    NEVER_HAPPENS # does this happen?
                    mergeCount( BBB, errors['ByBook'], thisKey )
                else: # it's things like SFMs, Characters, Words, Headings, Notes
                    for anotherKey in errors['ByBook'][BBB][thisKey]:
                        #print( " anotherKey", BBB, anotherKey )
                        if anotherKey.endswith('Errors') or anotherKey.endswith('List') or anotherKey.endswith('Lines'):
                            assert( isinstance( errors['ByBook'][BBB][thisKey][anotherKey], list ) )
                            appendList( BBB, errors['ByBook'], thisKey, anotherKey )
                            if anotherKey not in errors['ByCategory'][thisKey]: errors['ByCategory'][thisKey][anotherKey] = []
                            errors['ByCategory'][thisKey][anotherKey].extend( errors['ByBook'][BBB][thisKey][anotherKey] )
                        elif anotherKey.endswith('Counts'):
                            mergeCount( BBB, errors['ByBook'], thisKey, anotherKey )
                            # Haven't put counts into category array yet
                        else:
                            print( anotherKey, "not done yet" )
                            #halt # Not done yet

        # Taking those word lists, find uncommon words
        threshold = 4 # i.e., find words used less often that this many times as possible candidates for spelling errors
        uncommonWordCounts = {}
        if 'Words' in errors['ByBook']['All Books']:
            for word, lcCount in errors['ByBook']['All Books']['Words']['Case Insensitive Word Counts'].items():
                adjWord = word
                if word not in errors['ByBook']['All Books']['Words']['All Word Counts'] \
                or errors['ByBook']['All Books']['Words']['All Word Counts'][word] < lcCount: # then it sometimes occurs capitalized in some way
                    # Look for uncommon capitalizations
                    results = getCapsList( word, lcCount, errors['ByBook']['All Books']['Words']['All Word Counts'] )
                    if len(results) > 2:
                        if 'Possible Word Errors' not in errors['ByBook']['All Books']['Words']: errors['ByBook']['All Books']['Words']['Possible Word Errors'] = []
                        errors['ByBook']['All Books']['Words']['Possible Word Errors'].append( _("Lots of ways of capitalizing {}").format( results ) )
                if lcCount < threshold: # look for uncommon words
                    if word not in errors['ByBook']['All Books']['Words']['All Word Counts']: # then it ONLY occurs capitalized in some way
                        adjWord = getCapsList( word, lcCount, errors['ByBook']['All Books']['Words']['All Word Counts'] )[0]
                    uncommonWordCounts[adjWord] = lcCount
            if uncommonWordCounts: errors['ByBook']['All Books']['Words']['Uncommon Word Counts'] = uncommonWordCounts
            
    	# Remove any unnecessary empty categories
        for category in errors['ByCategory']:
            if not errors['ByCategory'][category]:
                #print( "InternalBible.getErrors: Removing empty category", category, "from errors['ByCategory']" )
                del errors['ByCategory'][category]
        return errors
    # end of getErrors
# end of class InternalBible


def main():
    """
    Demonstrate reading and checking some Bible databases.
    """
    # Handle command line parameters
    from optparse import OptionParser
    parser = OptionParser( version="v{}".format( versionString ) )
    #parser.add_option("-e", "--export", action="store_true", dest="export", default=False, help="export the XML file to .py and .h tables suitable for directly including into other programs")
    Globals.addStandardOptionsAndProcess( parser )

    if Globals.verbosityLevel > 0: print( "{} V{}".format( progName, versionString ) )

    # Since this is only designed to be a base class, it can't actually do much at all
    IB = InternalBible( "Test internal Bible", False ) # The second parameter is the logErrorsFlag
    IB.objectNameString = "Dummy test Internal Bible object"
    IB.sourceFolder = "Nowhere"
    if Globals.verbosityLevel > 0: print( IB )
if __name__ == '__main__':
    main()
## End of InternalBible.py
