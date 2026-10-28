"""Recognizing ticket keys in spreadsheet comments, including the clean-up of typos and old ticket numbers."""

import re
from dataclasses import dataclass

TICKET_PREFIXES = ('KP', 'TNG', 'ENGINE', 'AGA', 'MSI')
_PREFIX = '|'.join(TICKET_PREFIXES)
TICKET = re.compile(rf'\b(?:{_PREFIX})-[1-9]\d*\b')
TNG_FROM = 4000  # bare numbers like '#4138' from 4000 on are TNG tickets, lower ones KP tickets

# Obvious typos, corrected without a review flag; applied in this order.
_TYPOS = (
    (re.compile(r'\bEINGINE-'), 'ENGINE-'),  # 'EINGINE-461'
    (re.compile(rf'#\s?({_PREFIX})-'), r'\1-'),  # '#KP-1494'
    (re.compile(rf'\b(?:{_PREFIX})\s+(?=(?:{_PREFIX})-\d)'), ''),  # 'TNG TNG-4828'
    (re.compile(rf'\b({_PREFIX})\s?(\d+)\b'), r'\1-\2'),  # 'TNG 5212', 'TNG4840', 'KP1895'
    (re.compile(rf'\b({_PREFIX})-0+(\d+)'), r'\1-\2'),  # 'MSI-02'
)
# Uncertain cases, corrected and flagged for review.
_FOLLOWING = re.compile(rf'\b((?:{_PREFIX})-\d+)ff\b')  # 'TNG-2035ff' ("fortfolgend")
_ALIAS = re.compile(r'#\s?(\d+)\s*(?:aka|/)\s*#\s?(\d+)')  # '#4347 aka #1482', '#4347/#1482'
_BARE = re.compile(r'#\s?(\d+)\b')  # '#4138', '# 4251'


@dataclass(frozen=True)
class CleanedText:
    text: str
    uncertain: bool = False  # a ticket key was guessed: flag the entries for review
    corrected: bool = False  # an obvious typo was corrected
    aliases: tuple[str, ...] = ()  # second keys of the same ticket ('#4347 aka #1482' → 'KP-1482')


def bare_key(number: str) -> str:
    """'4138' → 'TNG-4138', '1482' → 'KP-1482'."""
    return f'TNG-{int(number)}' if int(number) >= TNG_FROM else f'KP-{int(number)}'


def clean_tickets(text: str) -> CleanedText:
    """Text with ticket keys in proper form, e.g. '#4347 aka #1482 add impersonation' → 'TNG-4347 add impersonation'."""
    original = text
    for pattern, replacement in _TYPOS:
        text = pattern.sub(replacement, text)
    corrected = text != original
    aliases = tuple(bare_key(match[2]) for match in _ALIAS.finditer(text))
    text, following = _FOLLOWING.subn(r'\1', text)
    text, aliased = _ALIAS.subn(lambda match: bare_key(match[1]), text)
    text, bare = _BARE.subn(lambda match: bare_key(match[1]), text)
    return CleanedText(text, bool(following or aliased or bare), corrected, aliases)


def find_tickets(text: str) -> list[str]:
    """Distinct ticket keys in order of appearance."""
    return list(dict.fromkeys(TICKET.findall(text)))
