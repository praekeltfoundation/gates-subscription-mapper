=========================
Gates Subscription Mapper
=========================

A component for moving subscriptions from one message set to another.

More specifically, given a db table of UUIDs, migrates those subscriptions from
their existing message set to a new message set, and given a UUID through a
webhook, moves that subscription from the new message set back to the old
message set.
