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

The counterexample identifies the shared natural-join columns and the relations that carry them in `join_attributes`. For each overlapping pair, the verifier joins its projected witness rows on all shared columns. If none of the source rows has the same values on the pair's combined columns, the verifier adds the pair to `spurious_join_pairs` with its `relations` and `join_values`. In the example above, the feedback says that joining `R` and `S` on `B=0` produces a spurious combination. A multiway counterexample can require the full join, so the feedback lists every shared column even when no pair produces a spurious combination by itself. With completely disjoint relations, the join is a Cartesian product. When the pipeline retries, it includes this feedback text in the next schema request.

The verifier projects the source rows onto each proposed relation to build `example_tables`, with a sorted list of distinct rows for each relation. `join_traces` contains one trace for the `spurious_tuple`. Each step records the `relation`, its 1-based `row_number` in that table, and the `join_values` for columns shared with the result so far. The trace starts with the first relation in the schema, then prefers a remaining relation with shared columns. A later step with no shared columns is a Cartesian product. In this example, the trace starts with `R` row 1 `(A=0, B=0)` and joins `S` row 1 `(B=0, C=0)` on `B=0`.

If an extra row exists in any legal instance, a source row can be selected from that instance for each projection that contributes to the extra row. Keeping just those source rows preserves all the FDs. Values in each column can be renamed so the extra row has value `0` in that column, since the constraints use only within-column equality. Thus every lossy decomposition admits a model of the formula, and an unsatisfiable result proves losslessness for the entire decomposition.

## Dependency preservation

The projection of `F` on `Rᵢ` consists of every FD implied by `F` whose attributes are all contained in `Rᵢ`. The decomposition preserves dependencies if the union of these projected FDs implies every original FD. `_preservation_violations` accepts dependencies whose columns all occur in one relation and uses the following steps for the others. [Database System Concepts, chapter 7](https://codex.cs.yale.edu/avi/db-book/slides-dir/PDF-dir/ch7.pdf)

1. Start with `S = X`.
2. For each relation `Rᵢ`, use `_Closure.of` to compute `(S ∩ Rᵢ)⁺` under `F`. Add the resulting attributes in `Rᵢ` to `S`.
3. Repeat until `Y` is contained in `S` or no attribute is added. If `Y` is contained in `S`, the original FD is preserved.

In each round, every addition follows from an FD that can be checked within a single relation. At the fixed point, any projected FD whose determinant is in `S` already has its dependents in `S`. This gives exactly the closure under the union of the projected FDs.

For example, let `F` contain `[A, B] -> [C]` and `[C] -> [B]`. With `R(A, C)` and `S(B, C)`, the procedure for `[A, B] -> [C]` starts at `[A, B]`. Within `R`, the available seed is `[A]`, which reaches only `[A]`. Within `S`, the seed is `[B]`, which reaches only `[B]`. `C` remains missing, so the FD fails preservation. The verifier reports two rows that agree exactly on the fixed-point set, here `(0, 0, 0)` and `(0, 0, 1)` in `A, B, C` order. These agree on the original determinant and differ on its dependent, while satisfying every projected FD.

For a dependency-preservation failure, `example_tables` contains the projections of those two source rows. The two entries in `join_traces` reconstruct them in `witness_rows` order. Here, `R` row 1 joins `S` row 1 on `C=0`, and `R` row 2 joins `S` row 2 on `C=1`.

## Result and feedback

`verify_schema` runs all four checks and groups findings by rule. Normal-form findings include relation names and declared column names. The decomposition and preservation counterexamples use logical attribute names so shared columns have a single entry per row. The result contains structured violation records and a readable `feedback` string for the planned LLM refinement step. Finding all minimal candidate keys and determinants can take exponential time when many such sets exist.

## Worked examples

Run an example's input block from the project root, then use the following code to print the verifier's feedback. The examples below show the generated feedback and how the verifier reaches it.

```python
from verifier.verify import verify_schema

print(verify_schema(relational_schema, functional_dependencies)["feedback"])
```

### 2NF violation in Enrollment

`Enrollment` stores a grade for each student and course pair. The title depends on the course ID alone.

```python
relational_schema = "Enrollment(<u>Student_Id</u>, <u>Course_Id</u>, Course_Title, Grade)"
functional_dependencies = [
    "[Course_Id] -> [Course_Title]",
    "[Student_Id, Course_Id] -> [Grade]",
]
```

The verifier derives the candidate key `[Course_Id, Student_Id]`. The closure of `[Course_Id]` contains the non-prime attribute `Course_Title`, so the feedback identifies a partial dependency on the `Course_Id` part of the key. The same closure leaves `Grade` and `Student_Id` unreached, which also gives a 3NF violation.

```text
Not verified.
2NF — Enrollment: [Course_Id] -> [Course_Title] is a partial dependency. The determinant is a proper subset of the following candidate keys: [Course_Id, Student_Id] (declared primary key). Course_Title is non-prime.
3NF — Enrollment: [Course_Id] -> [Course_Title] follows from the functional dependencies. The determinant cannot determine [Grade, Student_Id] in this relation, and Course_Title belongs to no candidate key.
```

### 3NF violation in Employee

Each employee ID determines the employee's department ID. Each department ID determines its name.

```python
relational_schema = "Employee(<u>Employee_Id</u>, Department_Id, Department_Name)"
functional_dependencies = [
    "[Employee_Id] -> [Department_Id]",
    "[Department_Id] -> [Department_Name]",
]
```

The verifier derives `[Employee_Id]` as the only candidate key. Starting from `[Department_Id]`, it reaches `Department_Name` and leaves `Employee_Id` unreached. The determinant therefore fails the superkey condition, and the dependent is non-prime. This example passes 2NF because the only proper subset of `[Employee_Id]` is the empty set, whose closure is empty.

```text
Not verified.
3NF — Employee: [Department_Id] -> [Department_Name] follows from the functional dependencies. The determinant cannot determine [Employee_Id] in this relation, and Department_Name belongs to no candidate key.
```

### Lossless decomposition violation for café offerings

Each café is in one city. The proposed decomposition keeps the café and city in one table and the city and drink in another.

```python
relational_schema = (
    "Cafe_City(<u>Cafe</u>, City)\n"
    "City_Drink(<u>City</u>, <u>Drink</u>)"
)
functional_dependencies = [
    "[Cafe] -> [City]",
]
```

Z3 finds two source rows where café `0` serves drink `1` and café `1` serves drink `0`. Both cafés are in city `0`. The verifier projects those rows into the two proposed tables, then traces the join that pairs café `0` with drink `0`. The joined tuple is extra because that pairing is absent from the source rows.

```text
Not verified.
lossless decomposition — Joining the projections can introduce a spurious tuple.
  Joining Cafe_City and City_Drink on City=0 produces a spurious combination absent from every source row.
  Source data before decomposition (satisfies all supplied dependencies)
    Source row 1: {'Cafe': 0, 'City': 0, 'Drink': 1}
    Source row 2: {'Cafe': 1, 'City': 0, 'Drink': 0}
  Example table rows before the join
    Cafe_City(Cafe, City)
      Row 1 (0, 0)
      Row 2 (1, 0)
    City_Drink(City, Drink)
      Row 1 (0, 0)
      Row 2 (0, 1)
  Join trace for the spurious tuple
    Start with Cafe_City row 1.
    Join City_Drink row 1 on City=0.
  Spurious tuple: {'Cafe': 0, 'City': 0, 'Drink': 0}
```

#### Café example with concrete values

The numbers in parentheses are the verifier's labels for the values in each column.

| Café | City | Drink |
| --- | --- | --- |
| River Café (`0`) | Edmonton (`0`) | Tea (`1`) |
| Oak Café (`1`) | Edmonton (`0`) | Coffee (`0`) |

`Cafe_City` row 1 keeps **River Café, Edmonton** from the first source row. `City_Drink` row 1 keeps **Edmonton, Coffee** from the second source row. They match on `City = Edmonton`, so the join produces **River Café, Edmonton, Coffee**. The source table lists tea for River Café, so this coffee row is spurious.

### Dependency preservation violation for student advisors

Each student can have at most one advisor per department, and each advisor belongs to one department. The proposed decomposition puts student–advisor pairs in one table and each advisor's department in another.

```python
relational_schema = (
    "Student_Advisor(<u>Student_Id</u>, <u>Advisor_Id</u>)\n"
    "Advisor(<u>Advisor_Id</u>, Department)"
)
functional_dependencies = [
    "[Student_Id, Department] -> [Advisor_Id]",
    "[Advisor_Id] -> [Department]",
]
```

Starting with `[Student_Id, Department]`, the verifier can use only `Student_Id` in `Student_Advisor` and only `Department` in `Advisor`. Neither yields `Advisor_Id` under the supplied dependencies. The verifier constructs two example rows that agree on the student and department and differ on the advisor. Their projections satisfy each table's local rules. The join traces show how those table rows produce the two conflicting advisor assignments.

```text
Not verified.
dependency preservation — [Student_Id, Department] -> [Advisor_Id] is not preserved. The dependencies enforceable in the individual relations can derive only [Department, Student_Id] from its determinant. The missing logical attributes are [Advisor_Id]. The FD's columns occur in Student_Advisor[Advisor_Id, Student_Id], Advisor[Advisor_Id, Department].
  Each example table satisfies its projected dependencies.
  Example table rows before the join
    Student_Advisor(Student_Id, Advisor_Id)
      Row 1 (0, 0)
      Row 2 (0, 1)
    Advisor(Advisor_Id, Department)
      Row 1 (0, 0)
      Row 2 (1, 0)
  Join trace for witness row 1
    Start with Student_Advisor row 1.
    Join Advisor row 1 on Advisor_Id=0.
  Joined row 1: {'Advisor_Id': 0, 'Department': 0, 'Student_Id': 0}
  Join trace for witness row 2
    Start with Student_Advisor row 2.
    Join Advisor row 2 on Advisor_Id=1.
  Joined row 2: {'Advisor_Id': 1, 'Department': 0, 'Student_Id': 0}
  The joined rows agree on Department=0, Student_Id=0 and differ on Advisor_Id (0 versus 1).
```

#### Advisor example with concrete values

Read `Student_Id=0` as student `101` and `Department=0` as Computing. Read `Advisor_Id=0` and `Advisor_Id=1` as advisors `A10` and `A20`, respectively.

| Row | `Student_Advisor` (`Student_Id`, `Advisor_Id`) | `Advisor` (`Advisor_Id`, `Department`) |
| --- | --- | --- |
| 1 | (`101`, `A10`) | (`A10`, Computing) |
| 2 | (`101`, `A20`) | (`A20`, Computing) |

Joining on `Advisor_Id` matches the first pair of rows on `A10` and the second pair on `A20`. The joined rows are `(101, Computing, A10)` and `(101, Computing, A20)` in student, department, advisor order. The same student and department now have two different advisors, which violates `[Student_Id, Department] -> [Advisor_Id]`.
