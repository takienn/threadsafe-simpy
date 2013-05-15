"""
This module contains all :class:`Store` like resources.

Stores model the production and consumption of concrete Python objects.

The type of items you can put into or get from the store is not defined.
You can use normal Python objects, SimPy processes or other resources.
You can even mix them as you want.

Beside :class:`Store`, there is a :class:`FilterStore` that lets you
use a custom function to filter the objects you get out of the store.

.. autoclass:: Store
.. autoclass:: FilterStore
.. autoclass:: StorePut
.. autoclass:: StoreGet
.. autoclass:: FilterStoreGet(resource, filter=lambda item: True)
.. autoclass:: FilterQueue

"""
from simpy.resources import base


class StorePut(base.Put):
    """This event type is used by :meth:`Store.put()`.

    .. attribute:: item

        The item to put into the store.

    """
    def __init__(self, resource, item):
        super(StorePut, self).__init__(resource)
        self.item = item


class StoreGet(base.Get):
    """This event type is used by :meth:`Store.get()`."""
    pass


class FilterStoreGet(StoreGet):
    """This event type is used by :meth:`FilterStore.get()`.

    .. attribute:: filter

        The filter function to use.

    """
    def __init__(self, resource, filter=lambda item: True):
        super(FilterStoreGet, self).__init__(resource)
        self.filter = filter


class FilterQueue(list):
    """The queue inherits :class:`list` and modfies
    :meth:`__getitem__()` and :meth:`__bool__` to appears to only
    contain events for which the *store*\ 's item queue contains proper
    item.

    .. automethod:: __getitem__
    .. automethod:: __bool__
    .. automethod:: __nonzero__

    """
    def __init__(self):
        super(FilterQueue, self).__init__()
        self.store = None

    def __getitem__(self, key):
        """Get the *key*\ th event from all events that have an item
        available in the corresponding store's item queue."""
        filtered_events = [evt for evt in self
                           if any(evt.filter(item)
                                  for item in self.store.items)]
        return filtered_events[key]

    def __bool__(self):
        """Return ``True`` if the queue contains an event for which an
        item is available in the corresponding store's item queue."""
        for evt in self:
            for item in self.store.items:
                if evt.filter(item):
                    return True
        return False

    #: Provided for backwards compatability: :meth:`__bool__()` is only
    #: used from Python 3 onwards.
    __nonzero__ = __bool__


class Store(base.BaseResource):
    """Models the production and consumption of concrete Python objects.

    The ``env`` parameter is the :class:`~simpy.core.Environment`
    instance the container is bound to.

    The ``capacity`` defines the size of the Store and must be
    a positive number (> 0). By default, a Store is of unlimited size.
    A :exc:`ValueError` is raised if the value is negative.

    .. autoattribute:: capacity

    .. attribute:: items

        List of the items within the store.

    .. method:: put(item)

        Put *item* into the store if possible or wait until it is.

    .. method:: get()

        Get an item from the store or wait until one is available.

    """
    PutEvent = StorePut
    GetEvent = StoreGet

    def __init__(self, env, capacity=1):
        super(Store, self).__init__(env)
        self._capacity = capacity
        self.items = []

    @property
    def capacity(self):
        """The maximum capacity of the store."""
        return self._capacity

    def _do_put(self, event):
        if len(self.items) < self._capacity:
            self.items.append(event.item)
            event.succeed()

    def _do_get(self, event):
        if self.items:
            event.succeed(self.items.pop(0))


class FilterStore(Store):
    """The *FilterStore* subclasses :class:`Store` and allows you to
    only get items that match a user-defined criteria.

    This criteria is defined via a filter function that is passed to
    :meth:`get()`. :meth:`get()` only considers items for which this
    function returns ``True``.

    .. note::

        In contrast to :class:`Store`, processes trying to get an item
        from :class:`FilterStore` won't necessarily be processed in the
        same order that they made the request.

        *Example:* The store is empty. *Process 1* tries to get an item
        of type *a*, *Process 2* an item of type *b*. Another process
        puts one item of type *b* into the store. Though *Process 2*
        made his request after *Process 1*, it will receive that new
        item because *Process 1* doesn't want it.

    .. method:: get(filter=lambda item: True)

        Get the first item from the store for which *filter* returns
        ``True``.

        The default *filter* function returns ``True`` for all items,
        and thus exactly behaves like :meth:`Store.get()`.

    """
    GetEvent = FilterStoreGet
    GetQueue = FilterQueue

    def __init__(self, env, capacity=1):
        super(FilterStore, self).__init__(env, capacity)
        self.get_queue.store = self

    def _do_get(self, event):
        for item in self.items:
            if event.filter(item):
                self.items.remove(item)
                event.succeed(item)
                break
