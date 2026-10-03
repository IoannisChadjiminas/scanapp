"""One auxiliary CPU lane: card-region work takes priority over label retries."""
from contextlib import contextmanager
from threading import Condition

from app.recognition.grading_control import check_grading_cancelled


class AuxiliaryWorkGate:
    """Main recognition + at most one auxiliary inference, with no backlog.

    Never interrupt an in-flight model call. Between calls, optional grading
    yields to a waiting card-region read. Independent readers still own their
    mutable OCR state; this gate schedules CPU work, not evidence sharing.
    """
    def __init__(self):
        self.condition = Condition()
        self.active = False
        self.card_waiters = 0

    def try_reserve_card(self):
        """Never make a card read wait behind an optional grading call."""
        with self.condition:
            if self.active or self.card_waiters:
                return False
            self.active = True
            return True

    def release_card(self):
        with self.condition:
            self.active = False
            self.condition.notify_all()

    @contextmanager
    def card(self):
        with self.condition:
            self.card_waiters += 1
            self.condition.notify_all()
            try:
                while self.active:
                    self.condition.wait()
                self.active = True
            finally:
                self.card_waiters -= 1
        try:
            yield
        finally:
            with self.condition:
                self.active = False
                self.condition.notify_all()

    @contextmanager
    def grading(self):
        with self.condition:
            while self.active or self.card_waiters:
                check_grading_cancelled()
                self.condition.wait(.05)
            check_grading_cancelled()
            self.active = True
        try:
            yield
        finally:
            with self.condition:
                self.active = False
                self.condition.notify_all()
