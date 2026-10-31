-- Fictional wells and a realistic sensor catalog for a gas-lifted oil field.
-- Values are illustrative, not from any real asset.

INSERT INTO core.wells (well_id, field, lift_type) VALUES
    ('W-01', 'Demo Field', 'gas_lift'),
    ('W-02', 'Demo Field', 'gas_lift'),
    ('W-03', 'Demo Field', 'natural');

--                       tag      description                              unit      min   max    alarm_low alarm_high
INSERT INTO core.tags VALUES
    ('WHP',     'Wellhead pressure',                     'bar',     0,    400,   20,   180),
    ('WHT',     'Wellhead temperature',                  'degC',  -10,    150,   30,    95),
    ('FLP',     'Flowline pressure',                     'bar',     0,    200,   10,    60),
    ('CHOKE',   'Choke opening',                         '%',       0,    100, NULL,  NULL),
    ('GL_RATE', 'Gas-lift injection rate',               'Sm3/d',   0, 200000, 5000, 120000);
