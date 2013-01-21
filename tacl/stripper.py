import logging
import os
import re
import sys

from lxml import etree


text_name_pattern = re.compile(
    r'^(?P<prefix>[A-Z]{1,2})\d+n(?P<text>[^_\.]+)_(?P<part>\d+)$')
# I do not understand what these are, but the spec called for them not
# to be used in the n-grams, and it is easier to remove them here than
# discard them in the tokenisation process, though presumably they are
# part of the text.
raw_code_removal_re = re.compile(r'&[^;]*;')

STRIP_XSLT = '''
<xsl:stylesheet extension-element-prefixes="fn my str"
                version="1.0"
                xmlns:fn="http://exslt.org/functions"
                xmlns:my="urn:foo"
                xmlns:str="http://exslt.org/strings"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output encoding="UTF-8" method="text" />
  <xsl:strip-space elements="*" />
  <xsl:template match="teiHeader" />
  <xsl:template match="note[@place != 'inline']" />
  <xsl:template match="gaiji">
    <xsl:choose>
      <xsl:when test="@des">
        <xsl:value-of select="@des" />
      </xsl:when>
      <xsl:when test="@udia">
        <xsl:value-of select="@sdchar" />
      </xsl:when>
      <xsl:when test="@uni">
        <xsl:value-of select="my:decode-codepoint(@uni)" />
      </xsl:when>
      <xsl:when test="@cb">
        <xsl:text>[</xsl:text>
        <xsl:value-of select="@cb" />
        <xsl:text>]</xsl:text>
      </xsl:when>
      <xsl:otherwise>
        <xsl:text>GAIJI WITHOUT REPRESENTATION</xsl:text>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>
  <xsl:template match="head[@type='no']" />
  <xsl:template match="item">
    <xsl:text>   </xsl:text>
    <xsl:apply-templates select="node()" />
  </xsl:template>
  <xsl:template match="l">
    <xsl:text>   </xsl:text>
    <xsl:apply-templates select="node()" />
  </xsl:template>
  <xsl:template match="lb[not(local-name(following-sibling::node()[1])='lb')]">
    <xsl:text>
</xsl:text>
  </xsl:template>
  <xsl:template match="div|lg|p|list">
    <xsl:text>
</xsl:text>
    <xsl:apply-templates select="node()" />
  </xsl:template>
  <xsl:template match="rdg" />
  <xsl:template match="text()">
    <xsl:value-of select="normalize-space()" />
  </xsl:template>
  <!-- The following functions are by Aristotle Pagaltzis, at
       http://plasmasturm.org/log/386/ -->
  <fn:function name="my:hex2num">
    <xsl:param name="hexstr" />
    <xsl:variable name="head"
                  select="substring( $hexstr, 1, string-length( $hexstr ) - 1 )"
    />
    <xsl:variable name="nybble"
                  select="substring( $hexstr, string-length( $hexstr ) )" />
    <xsl:choose>
      <xsl:when test="string-length( $hexstr ) = 0">
        <fn:result select="0" />
      </xsl:when>
      <xsl:when test="string( number( $nybble ) ) = 'NaN'">
        <fn:result select="
          my:hex2num( $head ) * 16
          + number( concat( 1, translate( $nybble, 'ABCDEF', '012345' ) ) )
        "/>
      </xsl:when>
      <xsl:otherwise>
        <fn:result select="my:hex2num( $head ) * 16 + number( $nybble )" />
      </xsl:otherwise>
    </xsl:choose>
  </fn:function>
  <fn:function name="my:num2hex">
    <xsl:param name="num" />
    <xsl:variable name="nybble" select="$num mod 16" />
    <xsl:variable name="head" select="floor( $num div 16 )" />
    <xsl:variable name="rest">
      <xsl:if test="not( $head = 0 )">
        <xsl:value-of select="my:num2hex( $head )"/>
      </xsl:if>
    </xsl:variable>
    <xsl:choose>
      <xsl:when test="$nybble > 9">
        <fn:result select="concat(
          $rest,
          translate( substring( $nybble, 2 ), '012345', 'ABCDEF' )
        )"/>
      </xsl:when>
      <xsl:otherwise>
        <fn:result select="concat( $rest, $nybble )" />
      </xsl:otherwise>
    </xsl:choose>
  </fn:function>
  <fn:function name="my:char-to-utf8bytes">
    <xsl:param name="codepoint" />
    <xsl:choose>
      <xsl:when test="$codepoint > 65536">
        <fn:result select="
            ( ( floor( $codepoint div 262144 ) mod  8 + 240 ) * 16777216 )
          + ( ( floor( $codepoint div   4096 ) mod 64 + 128 ) *    65536 )
          + ( ( floor( $codepoint div     64 ) mod 64 + 128 ) *      256 )
          + ( ( floor( $codepoint div      1 ) mod 64 + 128 ) *        1 )
        " />
      </xsl:when>
      <xsl:when test="$codepoint > 2048">
        <fn:result select="
            ( ( floor( $codepoint div   4096 ) mod 16 + 224 ) *    65536 )
          + ( ( floor( $codepoint div     64 ) mod 64 + 128 ) *      256 )
          + ( ( floor( $codepoint div      1 ) mod 64 + 128 ) *        1 )
        " />
      </xsl:when>
      <xsl:when test="$codepoint > 128">
        <fn:result select="
            ( ( floor( $codepoint div     64 ) mod 32 + 192 ) *      256 )
          + ( ( floor( $codepoint div      1 ) mod 64 + 128 ) *        1 )
        " />
      </xsl:when>
      <xsl:otherwise>
        <fn:result select="$codepoint" />
      </xsl:otherwise>
    </xsl:choose>
  </fn:function>
  <fn:function name="my:percentify">
    <xsl:param name="str" />
    <xsl:choose>
      <xsl:when test="string-length( $str ) > 2">
        <fn:result select="concat(
          '%',
          substring( $str, 1, 2 ),
          my:percentify( substring( $str, 3 ) )
        )" />
      </xsl:when>
      <xsl:otherwise>
        <fn:result select="concat( '%', $str )" />
      </xsl:otherwise>
    </xsl:choose>
  </fn:function>
  <fn:function name="my:decode-codepoint">
    <xsl:param name="codepoint" />
    <fn:result
      select="str:decode-uri( my:percentify(
        my:num2hex( my:char-to-utf8bytes(
          my:hex2num( $codepoint )
        ) )
      ) )"
    />
  </fn:function>
</xsl:stylesheet>'''


class Stripper (object):

    """Class used for preprocessing a corpus of texts by stripping out
    all material that is not the textual material proper.

    The intention is to keep the stripped text as close in formatting
    to the original as possible, including whitespace."""

    def __init__ (self, input_dir, output_dir):
        self._input_dir = os.path.abspath(input_dir)
        self._output_dir = os.path.abspath(output_dir)
        self._transform = etree.XSLT(etree.XML(STRIP_XSLT))
        self._texts = {}

    def _correct_entity_file (self, filename):
        """Adds an unused entity declaration to the entity file for
        `filename`, in the hopes that this will make it not cause a
        validation failure."""
        entity_filename = '%s.ent' % filename.split('_')[0]
        with open(entity_filename, 'rU') as input_file:
            text = input_file.read()
        with open(entity_filename, 'w') as output_file:
            output_file.write(text)
            output_file.write('<!ENTITY DUMMY_ENTITY "" >')

    def extract_text_name (self, filename):
        """Returns the name of the text in `filename`.

        Many texts are divided into multiple parts that need to be
        joined together.

        """
        basename = os.path.splitext(os.path.basename(filename))[0]
        match = text_name_pattern.search(basename)
        if match is None:
            logging.warn('Found an anomalous filename "%s"' % filename)
            return None, None
        text_name = '%s%s.txt' % (match.group('prefix'), match.group('text'))
        return text_name, int(match.group('part'))

    def strip_files (self):
        if not os.path.exists(self._output_dir):
            try:
                os.makedirs(self._output_dir)
            except OSError, e:
                logging.error('Could not create output directory: %s' % e)
                sys.exit('Could not create output directory: %s' % e)
        for dirpath, dirnames, filenames in os.walk(self._input_dir):
            for filename in filenames:
                if os.path.splitext(filename)[1] == '.xml':
                    self.strip_file(os.path.join(dirpath, filename))
        for text in self._texts:
            parts = self._texts[text].keys()
            parts.sort()
            with open(text, 'w') as output_file:
                for part in parts:
                    output_file.write(self._texts[text][part])

    def strip_file (self, filename, tried=False):
        file_path = os.path.join(self._input_dir, filename)
        text_name, part_number = self.extract_text_name(filename)
        if text_name is None:
            logging.warn('Skipping file "%s"' % filename)
            return
        stripped_file_path = os.path.join(self._output_dir, text_name)
        logging.debug('Stripping file %s into %s' %
                      (file_path, stripped_file_path))
        try:
            text = str(self._transform(etree.parse(file_path)))
        except etree.XMLSyntaxError:
            logging.warn('XML file "%s" is invalid' % filename)
            if tried:
                return
            logging.warn('Retrying after modifying entity file')
            self._correct_entity_file(filename)
            self.strip_file(filename, True)
            return
        text_parts = self._texts.setdefault(stripped_file_path, {})
        text_parts[part_number] = text
