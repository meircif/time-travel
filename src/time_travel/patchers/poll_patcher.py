"""A patch to the select.poll object."""

from .basic_patcher import BasicPatcher

import select as select_lib
import mock


DEFAULT_EVENTMASK = select_lib.POLLIN | select_lib.POLLOUT | select_lib.POLLPRI


class MockPollObject(object):
    """A mock poll object."""

    def __init__(self, clock, events_pool):
        """Initialize the object."""
        self.clock = clock
        self.events_pool = events_pool

        self.poll_events = {}

    def register(self, fd, eventmask=DEFAULT_EVENTMASK):
        """Register a file descriptor with the fake polling object."""
        self.poll_events[fd] = eventmask

    def modify(self, fd, eventmask):
        """Modify an already registered fd's event mask."""
        if fd not in self.poll_events:
            raise IOError()

        self.poll_events[fd] = eventmask

    def unregister(self, fd):
        """Remove a file descriptor tracked by the fake polling object."""
        if fd not in self.poll_events:
            raise KeyError(fd)

        self.poll_events.pop(fd)

    def poll(self, timeout=None):
        """Poll the set of registered file descriptors.

        `timeout` is a value in milliseconds.
        """
        timestamp, fd_events = \
            self._get_earliest_events_for_waited_fds(timeout)

        if timestamp == float('inf'):
            raise ValueError('No relevant future events were set for infinite '
                             'timout')

        for fd, events in fd_events:
            for event in events:
                self.events_pool.remove_fd(timestamp, fd, event)

        self.clock.time = timestamp

        def _crunch_events(_event_set):
            out = 0
            for _event in _event_set:
                out |= _event
            return out

        return [(fd, _crunch_events(events)) for fd, events in fd_events]

    def _get_earliest_events_for_waited_fds(self, timeout=None):
        """Return a list of [(fd, set(events)), ...]."""
        if timeout is None or timeout < 0:
            timeout = float('inf')
        else:
            timeout = timeout / 1000.0

        timeout_timestamp = self.clock.time + timeout

        result_events = []
        result_timestamp = timeout_timestamp

        def _is_relevant_fd_event(fd, evt):
            return fd in self.poll_events and self.poll_events[fd] & evt

        # fd_events is a list of [(fd, set(events)), ...].
        for timestamp, fd_events in self.events_pool.get_events(
                _is_relevant_fd_event):
            if timestamp > timeout_timestamp:
                # No event before the timeout
                break

            if fd_events:
                result_events = fd_events
                result_timestamp = timestamp
                break

        return result_timestamp, result_events


class PollPatcher(BasicPatcher):
    """Patcher for select.poll."""
    
    def __init__(self, *args, **kwargs):
        """Create the patch."""
        super(PollPatcher, self).__init__(*args, **kwargs)

        self.patches = [mock.patch('select.poll', self._mock_poll)]
    
    def _mock_poll(self):
        return MockPollObject(self.clock, self.events_pool)
