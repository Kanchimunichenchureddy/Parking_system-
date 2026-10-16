# Learn before expanding ParkReceipt

This is a rough research MVP. Its purpose is to test whether a QR page and staff confirmation reduce paperwork without confusing customers. It has not established product demand or payment readiness.

## First experiment: one attendant, one location, ten participants

Use fictional plates and no phone numbers for the first rehearsal. Tell participants that this is a prototype. Have them scan the sign, read the fee, submit a cash request, show the reference to the attendant, and find their confirmed receipt. Use pretend cash during rehearsals and keep those records separate from any later operational dataset. Do not mix practice records with actual collections.

Observe without guiding at first. Record whether the person can complete each step, where they hesitate, whether they trust the confirmation, and whether they can retrieve their receipt later. Test a slow connection, a customer without a smartphone, a duplicate approval click, and two customers with similar vehicle numbers.

## What the software records

- Request creation time, location, quoted fee, method, and status.
- Confirmation time and the staff account responsible for cash approval.
- Failed, cancelled, pending and successful online simulations.
- Audit events for approvals, cancellations, rate changes and staff assignments.
- Owner CSV with matching date, location, method and search filters.

The dashboard shows mean cash confirmation time and percentage of filtered records confirmed. It does not measure sign views, scans, abandoned forms, actual vehicle arrival, occupancy, departures, customer satisfaction, or verified bank deposits. Dates use confirmation time for confirmed records and creation time for other records, so the displayed percentage is not a cohort conversion rate. Export and analyze a fixed creation cohort separately if that metric becomes necessary.

## Observation sheet

Use `research_observations.csv`; one row per participant. Use an anonymous participant ID, not a name or phone number. Measure elapsed seconds with a timer. Avoid recording identifiable vehicle numbers in notes. Keep raw application exports private and agree a deletion date before a pilot.

Questions after the task:

1. What did you expect after choosing cash?
2. How did you know payment was confirmed?
3. What would you do if the receipt did not appear?
4. Would you want this receipt later, and how would you find it?
5. For staff: what was slower or more error-prone than a paper slip?

## Decide what to build next

Set targets before observing results. Suggested hypotheses to test, not proven benchmarks: at least 8 of 10 people finish without help; no incorrect cash approvals; the attendant can match every reference to the correct payment; every participant understands online payment is simulated. Compare handling time with the current paper process.

If scanning or data entry is the bottleneck, simplify the customer page. If staff confirmation is the bottleneck, improve queue matching and staff training. If receipt retrieval matters, research a consent-based delivery channel. Add a verified live gateway only after these workflow questions are understood. Exit tracking would require a separate staff-confirmed flow.

Before an actual-money pilot: run the suite against isolated MySQL, test real phones on the intended network, use HTTPS and secure cookies, assign individual credentials, back up and restore the database, define data retention, and reconcile cash with the attendant's physical count. The current app does not claim production or live online payment readiness.
