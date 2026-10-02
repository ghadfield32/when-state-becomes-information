# Third-party attribution and terms

The package's software is licensed under the [MIT licence](LICENSE). SPL data
and data-derived research artifacts have separate terms; the code licence does
not grant commercial rights to those materials.

## SPL Open Data

Credit: Maple Leaf Sports & Entertainment (MLSE), Sport Performance Lab (SPL),
Toronto, Ontario, Canada.

Source: [SPL Open Data](https://github.com/Sport-Performance-Lab/SPL-Open-Data).
Revision used: `a3f9cffbde917b1e1747cedd6ec25dfab18c6051`.
Historical upstream URL preserved in its README:
[mlsedigital/SPL-Open-Data](https://github.com/mlsedigital/SPL-Open-Data).

Licence: [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-nc-sa/4.0/).
The unchanged upstream [SPL_LICENSE.txt](spl_data/SPL_LICENSE.txt) also states
the additional professional-sports/financial-analysis-firm exclusion requiring
the stated specific written commercial (paid) licence for those parties' use.
That text is preserved, not waived or replaced by this package.

Modification statement: the optional downloader retrieves a subset of original
JSON trial files without modifying their bytes. The public manifest selects
only four E1 session/participant directories and retains original file hashes.
The study's aggregate reports and figures transform the source into forecasting
results and visualizations; software converts source positions from feet to
metres and computes the disclosed research features and summaries. Those
data-derived aggregates and figures are conservatively distributed under
CC BY-NC-SA 4.0 with the upstream additional exclusion preserved. Raw source
trials, fitted forecast stores and per-example derived arrays are not bundled.

Nothing here implies SPL/MLSE endorsement or blanket commercial clearance.
Review [DATA.md](DATA.md) and the complete source terms before use or
redistribution. Attribution, a public URL, and the MIT code licence do not
establish a user's eligibility under the SPL terms.
