# 02 – Realistic environments

Eight domains where the work is realistic and the environment only needs CPU. Each one is a Docker container, some messy but believable files, and a checker script with a clear pass/fail.

| # | Domain | Task | Verifier |
|---|---|---|---|
| 1 | **Tax return prep** | Folder of W-2s, 1099s, receipts, a K-1 (some scanned PDFs) → fill out the return | Run a tax engine (e.g. OpenTaxSolver) on the true inputs, compare line by line |
| 2 | **Month-end accounting close** | General ledger + bank statement CSVs + AR/AP aging → reconcile, post correcting entries, flag anomalies | Books balance; each planted error (duplicate payment, transposed amount) was found |
| 3 | **Industrial control (PLC)** | Write or fix ladder logic / structured text for a simulated tank-fill line or conveyor interlock | OpenPLC + a small Python plant model; run scenarios (sensor failure, e-stop) and check safety invariants |
| 4 | **PCB design-rule fixes** | KiCad board failing design-rule / electrical-rule checks → fix without changing what the circuit does | KiCad's command-line checks + netlist comparison |
| 5 | **Lab instrument data** | Raw plate reader / qPCR / mass spec exports with vendor quirks, bad wells, wrong metadata → concentrations or fold-changes | Compare to ground truth from the data generator, within tolerance |
| 6 | **Logistics disruption re-planning** | Port closure or truck breakdown → re-route shipments via a mock warehouse API and constraint spreadsheets | Plan is feasible and within X% of an OR-Tools optimum |
| 7 | **Zoning compliance review** | Parcel shapefiles, building footprints, zoning code in plain text → which permits violate setback / height / lot-coverage | Exact answers computed with geopandas |
| 8 | **Clinical record reconciliation** | Duplicate patient records across FHIR/HL7 feeds (typos, moves, conflicting med lists) → merged record + clean medication list | Synthetic ground-truth patients (e.g. Synthea); no real patient data |

## Notes

- **Best starting points:** tax prep (#1) for the cleanest verifier and adjustable messiness; PLC (#3) for novelty, since "don't violate safety invariants" is a strong reward signal.
- **The cost of realism is fixture-building.** Generating convincingly messy documents is most of the work. Once the generator exists, task variants are nearly free.
- **TODO:** check Harbor's registry for overlap before building.
