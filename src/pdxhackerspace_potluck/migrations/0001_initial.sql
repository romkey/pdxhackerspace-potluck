CREATE TABLE rsvps (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text        NOT NULL,
    party_size  integer     NOT NULL DEFAULT 1,
    note        text        NOT NULL DEFAULT '',
    token       text        NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dishes (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rsvp_id   integer NOT NULL REFERENCES rsvps (id) ON DELETE CASCADE,
    category  text    NOT NULL,
    dish      text    NOT NULL DEFAULT ''
);

CREATE INDEX dishes_rsvp_id_idx ON dishes (rsvp_id);
