# How the Z3 verifier works

`verify_schema` reads the proposed relations and the original functional dependencies (FDs). The same case-sensitive name in different relations denotes one logical attribute. Let `U` be the union of the attribute names, `Rᵢ` the attributes of one proposed relation, and `F` the original FDs. The verifier treats each `Rᵢ` as a projection of the same universal relation over `U`.

The checks use the relational model with set semantics and equality of attribute values. The supplied FDs define the constraints on the universal relation. Underlined columns identify the declared primary key for feedback. Candidate keys for the formal checks come from `F`. A verdict applies to this supplied model, so the caller needs to supply the intended FDs and shared attributes. An attribute omitted from both the candidate and the FDs is outside the input model.

## Attribute closure in Z3

`_Closure` builds one reusable Boolean encoding. The closure `X⁺` of a set `X` contains every attribute determined by `X` under `F`. Z3 starts with one Boolean per attribute indicating membership in `X`. At each step, an attribute is reached if it was already reached or an FD that determines it had its entire left side reached at the previous step. The solver equates each step's Boolean with this rule, so a model can include only attributes reached by the recurrence. An empty FD determinant is always satisfied.

Every step before stabilization adds at least one attribute. After `|U|` steps, the reachability Booleans therefore give the full closure. For example, with `[A] -> [B]` and `[B] -> [C]`, the seed `[A]` reaches `[A, B]` after one step and `[A, B, C]` after the second. `_Closure.of` fixes the seed and reads the result. The normal-form checks leave the seed symbolic so Z3 can search for sets with a given closure property.

For a local dependency `X -> a` in `Rᵢ`, the verifier restricts both `X` and `a` to `Rᵢ` and computes closure under all of `F`. This accounts for implications that pass through an attribute outside `Rᵢ`. With `[A] -> [B]` and `[B] -> [C]`, a relation containing `A` and `C` inherits `[A] -> [C]` even if it has no `B` column. [Database System Concepts, chapter 7](https://codex.cs.yale.edu/avi/db-book/slides-dir/PDF-dir/ch7.pdf)

## Second normal form (2NF)

A superkey of `Rᵢ` is an attribute set whose closure contains all of `Rᵢ`. A candidate key is an inclusion-minimal superkey. An attribute is prime if it belongs to any candidate key. A 2NF violation occurs when a proper subset of a candidate key determines a non-prime attribute of the same relation.

`_normal_form_violations` asks Z3 for the minimal seed sets in `Rᵢ` that are superkeys. `_Closure.minimal_sets` takes a satisfying set and asks whether a smaller set can satisfy the same condition. Once none can, it records the set and blocks it and its supersets from later searches. This finds every candidate key, including alternate keys. For each non-prime attribute, the verifier checks the minimal determinants described under 3NF and reports each that is a proper subset of some candidate key. This is complete because any proper-subset witness can be reduced to a minimal determinant inside that same key.

For example, suppose `R(A, B, C, D)` has `[A, B] -> [C]`, `[A, C] -> [B]`, and `[C] -> [D]`. The candidate keys are `[A, B]` and `[A, C]`. `D` is non-prime and `[C]` is a proper subset of `[A, C]`, so `[C] -> [D]` violates 2NF even if `[A, B]` is the declared primary key.

## Third normal form (3NF)

A local FD `X -> a` violates 3NF when `a` is outside `X`, `X` is not a superkey of that relation, and `a` is non-prime. For every non-prime `a` in `Rᵢ`, the verifier uses Z3 to search for seeds from `Rᵢ` excluding `a` that reach `a` and leave at least one attribute of `Rᵢ` unreached. It reports the inclusion-minimal seeds and the columns they fail to determine. Taking a smaller determinant cannot turn a non-superkey into a superkey, so every 3NF violation has a minimal witness of this form. [Database System Concepts, chapter 7](https://codex.cs.yale.edu/avi/db-book/slides-dir/PDF-dir/ch7.pdf)

In `Employee(Employee_Id, Dept_Id, Dept_Name)` with `[Employee_Id] -> [Dept_Id]` and `[Dept_Id] -> [Dept_Name]`, the only candidate key is `[Employee_Id]`. The closure of `[Dept_Id]` is `[Dept_Id, Dept_Name]`. It misses `Employee_Id`, and `Dept_Name` is non-prime, so the FD violates 3NF. The empty subset of `[Employee_Id]` determines nothing here, so 2NF passes.

## Lossless decomposition

A decomposition is lossless if, for every universal relation satisfying `F`, joining its projections gives exactly the original rows. Each original row always appears in the join. `_lossless_violations` uses Z3 to search for an extra row that the join could produce. [Database System Concepts, chapter 7](https://codex.cs.yale.edu/avi/db-book/slides-dir/PDF-dir/ch7.pdf)

The target extra row uses `0` in every column. The verifier creates one symbolic source row over `U` for each `Rᵢ`. Each source row must agree with the target on its own `Rᵢ` and differ from it in at least one column. For every pair of source rows and each `X -> Y` in `F`, agreement on `X` must imply agreement on `Y`.

If the formula is satisfiable, the model gives source rows that obey `F` and an extra row produced by their projections. For example, with `R(A, B)`, `S(B, C)` and `[A] -> [B]`, the source rows `(0, 0, 1)` and `(1, 0, 0)` satisfy the FD. Their `R` and `S` projections respectively contain `(0, 0)` on `A, B` and `(0, 0)` on `B, C`, yielding `(0, 0, 0)` in the join.

If an extra row exists in any legal instance, a source row can be selected from that instance for each projection that contributes to the extra row. Keeping just those source rows preserves all the FDs. Values in each column can be renamed so the extra row has value `0` in that column, since the constraints use only within-column equality. Thus every lossy decomposition admits a model of the formula, and an unsatisfiable result proves losslessness for the entire decomposition.

## Dependency preservation

The projection of `F` on `Rᵢ` consists of every FD implied by `F` whose attributes are all contained in `Rᵢ`. The decomposition preserves dependencies if the union of these projected FDs implies every original FD. `_preservation_violations` accepts dependencies whose columns all occur in one relation and uses the following steps for the others. [Database System Concepts, chapter 7](https://codex.cs.yale.edu/avi/db-book/slides-dir/PDF-dir/ch7.pdf)

1. Start with `S = X`.
2. For each relation `Rᵢ`, use `_Closure.of` to compute `(S ∩ Rᵢ)⁺` under `F`. Add the resulting attributes in `Rᵢ` to `S`.
3. Repeat until `Y` is contained in `S` or no attribute is added. If `Y` is contained in `S`, the original FD is preserved.

In each round, every addition follows from an FD that can be checked within a single relation. At the fixed point, any projected FD whose determinant is in `S` already has its dependents in `S`. This gives exactly the closure under the union of the projected FDs.

For example, let `F` contain `[A, B] -> [C]` and `[C] -> [B]`. With `R(A, C)` and `S(B, C)`, the procedure for `[A, B] -> [C]` starts at `[A, B]`. Within `R`, the available seed is `[A]`, which reaches only `[A]`. Within `S`, the seed is `[B]`, which reaches only `[B]`. `C` remains missing, so the FD fails preservation. The verifier reports two rows that agree exactly on the fixed-point set, here `(0, 0, 0)` and `(0, 0, 1)` in `A, B, C` order. These agree on the original determinant and differ on its dependent, while satisfying every projected FD.

## Result and feedback

`verify_schema` runs all four checks and groups findings by rule. Normal-form findings include relation names and declared column names. The decomposition and preservation counterexamples use logical attribute names so shared columns have a single entry per row. The result contains structured violation records and a readable `feedback` string for the planned LLM refinement step. Finding all minimal candidate keys and determinants can take exponential time when many such sets exist.
