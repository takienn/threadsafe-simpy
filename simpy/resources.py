"""
This modules contains simpy's resource types:

- :class:`Resource`: Can be used by a limited number of processes at a
  time (e.g., a gas station with a limited number of fuel pumps).
- :class:`Container`: Models the production and consumption of a
  homogeneous, undifferentiated bulk. It may either be continuous (like
  water) or discrete (like apples).
- :class:`Store`: Allows the production and consumption of discrete
  Python objects.

  TODO: add more documentation.

"""
from simpy.queues import FIFO


Infinity = float('inf')


class Resource(object):
    """A resource has a limited number of slots that can be requested
    by a process.

    If all slots are taken, requesters are put into
    a queue. If a process releases a slot, the next process is popped
    from the queue and gets one slot.

    For example, a gas station has a limited number of fuel pumps
    that can be used by refueling vehicles. If all fuel pumps are
    occupied, incoming vehicles have to wait until one gets free.

    The ``env`` parameter is the :class:`~simpy.core.Environment`
    instance the resource is bound to.

    The ``capacity`` defines the number of slots and must be a positive
    integer.

    The ``queue`` must provide a ``pop()`` method to get one item from
    it and a ``push(item)`` method to append an item. simpy comes with
    a :class:`~simpy.queues.FIFO` (which is used as a default),
    :class:`~simpy.queues.LIFO` and a :class:`~simpy.queues.Priority`
    queue.

    You can get the list of users via the :attr:`users` attribute and
    the queue of waiting processes via :attr:`queue`. You should not
    change these, though.

    """
    def __init__(self, env, capacity, queue=None):
        self._env = env

        self.capacity = capacity
        """The resource's maximum capacity."""

        self.queue = FIFO() if queue is None else queue
        """The queue of waiting processes. Read only."""

        self.users = []
        """The list of the resource's users. Read only."""

    def request(self, *q_args, **q_kwargs):
        """Request the resource.

        If the maximum capacity of users is not reached, the requesting
        process obtains the resource immediately (that is, a new event
        for it will be scheduled at the current time. That means that
        all other events also scheduled for the current time will be
        processed before that new event.).

        If the maximum capacity is reached, suspend the requesting
        process until another process releases the resource again.

        """
        event = self._env.event()
        proc = self._env.active_process

        if len(self.users) < self.capacity:
            self.users.append(proc)
            event.succeed()
        else:
            self.queue.push((event, proc), *q_args, **q_kwargs)

        return event

    def release(self):
        """Release the resource for the active process.

        Raise a :exc:`ValueError` if the process did not request the
        resource in the first place.

        If another process is waiting for the resource, resume that
        process.

        """
        proc = self._env.active_process
        try:
            self.users.remove(proc)
        except ValueError:
            # Check if the process is still waiting and remove it (this
            # happens if the process is interrupted while waiting).
            try:
                self.queue.remove(proc)
            except ValueError:
                # The process is neither in the users list nor in the queue
                raise ValueError('Cannot release resource for %s since it was '
                                 'not previously requested by it.' % proc)

        # Resume the next user if there is one
        if self.queue:
            event, next_user = self.queue.pop()
            self.users.append(next_user)
            event.succeed()


class Container(object):
    """Models the production and consumption of a homogeneous,
    undifferentiated bulk. It may either be continuous (like water) or
    discrete (like apples).

    For example, a gasoline station stores gas (petrol) in large tanks.
    Tankers increase, and refuelled cars decrease, the amount of gas in
    the station's storage tanks.

    The ``env`` parameter is the :class:`~simpy.core.Environment`
    instance the container is bound to.

    The ``capacity`` defines the size of the container and must be
    a positive number (> 0). By default, a container is of unlimited
    size.  You can specify the initial level of the container via
    ``init``. It must be >= 0 and is 0 by default. A :exc:`ValueError`
    is raised if one of these values is negative.

    A container has two queues: ``put_q`` is used for processes that
    want to put something into the container, ``get_q`` is for those
    that want to get something out. The default for both is
    :class:`~simpy.queues.FIFO`.

    """
    def __init__(self, env, capacity=Infinity, init=0, put_q=None, get_q=None):
        self._env = env

        if capacity <= 0:
            raise ValueError('capacity(=%s) must be > 0.' % capacity)
        if init < 0:
            raise ValueError('init(=%s) must be >= 0.' % init)

        self.capacity = capacity
        """The maximum capacity of the container. You should not change
        its value."""
        self._level = init

        self.put_q = put_q or FIFO()
        """The queue for processes that want to put something in. Read only."""
        self.get_q = get_q or FIFO()
        """The queue for processes that want to get something out. Read only.
        """

    @property
    def level(self):
        """The current level of the container (a number between ``0``
        and ``capacity``). Read only.

        """
        return self._level

    def put(self, amount):
        """Put ``amount`` into the Container if possible or wait until
        it is.

        Raise a :exc:`ValueError` if ``amount <= 0``.

        """
        if amount <= 0:
            raise ValueError('amount(=%s) must be > 0.' % amount)

        new_level = self._level + amount
        new_event = self._env.event()

        # Process can put immediately
        if new_level <= self.capacity:
            self._level = new_level

            # Pop processes from the "get_q".
            while self.get_q:
                event, proc, amount = self.get_q.peek()

                # Try to find another process if proc is no longer waiting.
                if proc.target is not event:
                    self.get_q.pop()
                    continue

                if self._level >= amount:
                    self.get_q.pop()
                    self._level -= amount
                    event.succeed()
                else:
                    break

            new_event.succeed()

        # Process has to wait.
        else:
            self.put_q.push((new_event, self._env.active_process, amount))

        return new_event

    def get(self, amount):
        """Get ``amount`` from the container if possible or wait until
        it is available.

        Raise a :exc:`ValueError` if ``amount <= 0``.

        """
        if amount <= 0:
            raise ValueError('amount(=%s) must be > 0.' % amount)

        new_event = self._env.event()

        # Process can get immediately
        if self._level >= amount:
            self._level -= amount

            # Pop processes from the "put_q".
            while self.put_q:
                event, proc, amout = self.put_q.peek()

                # Try to find another process if proc is no longer waiting.
                if proc.target is not event:
                    self.get_q.pop()
                    continue

                new_level = self._level + amount
                if new_level <= self.capacity:
                    self.put_q.pop()
                    self._level = new_level
                    event.succeed()
                else:
                    break

            new_event.succeed()

        # Process has to wait.
        else:
            self.get_q.push((new_event, self._env.active_process, amount))

        return new_event


class Store(object):
    """Models the production and consumption of concrete Python objects.

    The type of items you can put into or get from the store is not
    defined. You can use normal Python objects, SimPy processes or
    other resources. You can even mix them as you want.

    The ``env`` parameter is the :class:`~simpy.core.Environment`
    instance the container is bound to.

    The ``capacity`` defines the size of the Store and must be
    a positive number (> 0). By default, a Store is of unlimited size.
    A :exc:`ValueError` is raised if the value is negative.

    A container has three queues: ``put_q`` is used for processes that
    want to put something into the Store, ``get_q`` is for those that
    want to get something out. The ``item_q`` is used to store and
    retrieve the actual items. The default for all of them is
    :class:`~simpy.queues.FIFO`.

    """
    def __init__(self, env, capacity=Infinity, put_q=None, get_q=None,
                 item_q=None):
        self._env = env

        if capacity <= 0:
            raise ValueError('capacity(=%s) must be > 0.' % capacity)

        self.capacity = capacity
        """The maximum capacity of the Store. You should not change its
        value."""

        self.put_q = put_q or FIFO()
        """The queue for processes that want to put something in. Read only."""
        self.get_q = get_q or FIFO()
        """The queue for processes that want to get something out. Read only.
        """
        self.item_q = item_q or FIFO()
        """The queue that stores the items of the store. Read only."""

    @property
    def count(self):
        """The number of items in the Store (a number between ``0`` and
        ``capacity``). Read only.

        """
        return len(self.item_q)

    def put(self, item):
        """Put ``item`` into the Store if possible or wait until it is."""
        new_event = self._env.event()

        # Process can put immediately
        if len(self.item_q) < self.capacity:
            self.item_q.push(item)

            # Pop processes from the "get_q".
            while self.get_q and self.item_q:
                event, proc = self.get_q.pop()

                # Try to find another process if proc is no longer waiting.
                if proc.target is not event:
                    continue

                get_item = self.item_q.pop()
                event.succeed(get_item)

            new_event.succeed()

        # Process has to wait.
        else:
            self.put_q.push((new_event, self._env.active_process, item))

        return new_event

    def get(self):
        """Get an item from the Store or wait until one is available."""
        new_event = self._env.event()

        if len(self.item_q):
            item = self.item_q.pop()

            # Pop processes from the "push_q"
            while self.put_q and (len(self.item_q) < self.capacity):
                event, proc, put_item = self.put_q.pop()

                # Try to find another process if proc is no longer waiting.
                if proc._target is not event:
                    continue

                self.item_q.push(put_item)
                event.succeed()

            new_event.succeed(item)

        # Process has to wait
        else:
            self.get_q.push((new_event, self._env.active_process))

        return new_event
