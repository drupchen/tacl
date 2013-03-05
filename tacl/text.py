"""Module containing the Text class."""

import collections
import hashlib
import logging

from .tokenizer import tokenizer


class Text (object):

    def __init__ (self, filename, content, manager):
        self._filename = filename
        self._content = content
        self._manager = manager
        self._checksum = hashlib.md5(content).hexdigest()

    def add_label (self, label):
        """Adds `label` to the record of this text in the database."""
        self._manager.add_label(self._filename, label, self._checksum)

    def generate_ngrams (self, minimum, maximum):
        """Generates the n-grams (`minimum` <= n <= `maximum`) for
        this text.

        :param minimum: minimum n-gram size
        :type minimum: `int`
        :param maximum: maximum n-gram size
        :type maximum: `int`

        """
        logging.info('Generating n-grams ({} <= n <= {}) for {}'.format(
                minimum, maximum, self._filename))
        text_id = self._manager.add_text(self._filename, self._checksum)
        tokens = tokenizer.tokenize(self._content.decode('utf-8'))
        for size in range(minimum, maximum + 1):
            self._generate_ngrams(tokens, size, text_id)

    def _generate_ngrams (self, tokens, size, text_id):
        """Generates the n-grams of size `size` from `text`.

        :param tokens: tokens to generate n-grams from
        :type tokens: `list`
        :param size: size of the n-gram
        :type size: `int`
        :param text_id: id of text in database
        :type text_id: `int`

        """
        # Check that there aren't already n-grams of this size in the
        # database, in which case there is no need to generate them
        # again.
        if self._manager.has_ngrams(text_id, size):
            logging.info('{} already has {}-grams; not regenerating'.format(
                    self._filename, size))
        else:
            logging.info('Generating {}-grams for {}'.format(
                    size, self._filename))
            self._manager.add_text_ngram(text_id, size)
            counts = collections.Counter(self.ingrams(tokens, size))
            logging.info('There are {} unique {}-grams'.format(
                    len(counts), size))
            for ngram, count in counts.items():
                self._manager.add_ngram(text_id, ngram, size, count)
            self._manager.add_ngrams()

    @staticmethod
    def ingrams (sequence, degree):
        """Returns the n-grams generated from `sequence`, as an
        iterator.

        Base on the ingrams function from the Natural Language
        Toolkit.

        :param sequence: the source data to be converted into n-grams
        :type sequence: sequence or iter
        :param degree: the degree of the n-grams
        :type degree: int

        """
        sequence = iter(sequence)
        history = []
        while degree > 1:
            history.append(next(sequence))
            degree -= 1
        for item in sequence:
            history.append(item)
            yield ''.join(''.join(history).split())
            del history[0]
