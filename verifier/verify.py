"""Verify relational design properties under functional dependencies with Z3."""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
import re

import z3

from util.relational_schema import parse_identifier, parse_relational_schema


_FD = re.compile(r"\[([^\[\]]*)\]\s*->\s*\[([^\[\]]*)\]")


@dataclass(frozen=True)
class _Dependency:
    determinant: frozenset[str]
    dependents: frozenset[str]
    source: str


def parse_functional_dependencies(
    dependency_lines: Sequence[str] | str,
    attributes: set[str],
) -> list[_Dependency]:
    """Parse FD syntax and check all references against the given attributes."""
    if isinstance(dependency_lines, str):
        dependency_lines = dependency_lines.splitlines()
    if not isinstance(dependency_lines, Sequence):
        raise ValueError("Functional dependencies must be text or a sequence of strings.")

    dependencies = []
    for line_number, line in enumerate(dependency_lines, start=1):
        location = f"Functional dependency line {line_number}"
        if not isinstance(line, str):
            raise ValueError(f"{location}: expected a string.")
        line = line.strip()
        if not line:
            continue
        match = _FD.fullmatch(line)
        if match is None:
            raise ValueError(f"{location}: expected [A, B] -> [C].")
        left = []
        if match[1].strip():
            left = [parse_identifier(item, location) for item in match[1].split(",")]
        right = [parse_identifier(item, location) for item in match[2].split(",")]
        unknown = set(left + right) - attributes
        if unknown:
            raise ValueError(f"{location}: unknown attributes {_display(unknown)} in {line!r}.")
        dependencies.append(_Dependency(
            frozenset(left),
            frozenset(right),
            line,
        ))
    return dependencies


def _display(attributes):
    return "[" + ", ".join(sorted(attributes)) + "]"


def _satisfiable(solver, *assumptions):
    result = solver.check(*assumptions)
    if result == z3.unknown:
        raise RuntimeError(f"Z3 could not decide verification: {solver.reason_unknown()}")
    return result == z3.sat


class _Closure:
    """Symbolic least attribute closure for arbitrary starting sets under F."""

    def __init__(self, attributes, dependencies):
        self.solver = z3.Solver()
        self.seeds = {attribute: z3.Bool(f"seed_{i}") for i, attribute in enumerate(attributes)}
        rules = {attribute: [] for attribute in attributes}
        for dependency in dependencies:
            for attribute in sorted(dependency.dependents - dependency.determinant):
                rules[attribute].append(sorted(dependency.determinant))

        reached = self.seeds.copy()
        for step in range(len(attributes)):
            next_reached = reached.copy()
            for i, attribute in enumerate(attributes):
                if not rules[attribute]:
                    continue
                triggers = [z3.And(*(reached[item] for item in left)) for left in rules[attribute]]
                updated = z3.Bool(f"reached_{step}_{i}")
                self.solver.add(updated == z3.Or(reached[attribute], *triggers))
                next_reached[attribute] = updated
            reached = next_reached
        self.reached = reached

    def of(self, determinant):
        assumptions = [seed if attribute in determinant else z3.Not(seed)
                       for attribute, seed in self.seeds.items()]
        if not _satisfiable(self.solver, *assumptions):
            raise RuntimeError("The attribute-closure encoding rejected a fixed determinant.")
        model = self.solver.model()
        return frozenset(attribute for attribute, reached in self.reached.items()
                         if z3.is_true(model.eval(reached, model_completion=True)))

    def minimal_sets(self, allowed, condition):
        """Find all inclusion-minimal seed sets that satisfy a closure predicate."""
        self.solver.push()
        try:
            self.solver.add(condition, *(z3.Not(seed) for attribute, seed in self.seeds.items()
                                         if attribute not in allowed))
            minimal = []
            while _satisfiable(self.solver):
                chosen = self._model_seeds(allowed)
                for attribute in sorted(chosen):
                    if attribute not in chosen:
                        continue
                    trial = chosen - {attribute}
                    if _satisfiable(self.solver, *(z3.Not(seed) for item, seed in self.seeds.items()
                                                   if item not in trial)):
                        chosen = self._model_seeds(trial)
                minimal.append(frozenset(chosen))
                # A minimal set also rules out all its strict supersets.
                self.solver.add(z3.Or(*(z3.Not(self.seeds[item]) for item in sorted(chosen))))
            return sorted(minimal, key=lambda items: sorted(items))
        finally:
            self.solver.pop()

    def _model_seeds(self, allowed):
        model = self.solver.model()
        return {item for item in allowed
                if z3.is_true(model.eval(self.seeds[item], model_completion=True))}


def _normal_form_violations(relations, closure):
    second_nf = []
    third_nf = []
    for relation in relations:
        attributes = frozenset(relation.columns)
        superkey = z3.And(*(closure.reached[item] for item in relation.columns))
        candidate_keys = closure.minimal_sets(attributes, superkey)
        prime_attributes = frozenset().union(*candidate_keys)
        for dependent in sorted(attributes - prime_attributes):
            determinants = closure.minimal_sets(
                attributes - {dependent},
                z3.And(closure.reached[dependent], z3.Not(superkey)),
            )
            for determinant in determinants:
                left = sorted(determinant)
                right = dependent
                partial = [key for key in candidate_keys if determinant < key]
                if partial:
                    keys = ", ".join(
                        _display(key) + (" (declared primary key)" if key == relation.primary_key else "")
                        for key in partial
                    )
                    second_nf.append({
                        "relation": relation.name, "determinant": left, "dependent": right,
                        "candidate_keys": [sorted(key) for key in partial],
                        "message": (f"{relation.name}: {_display(left)} -> [{right}] is a partial "
                                    f"dependency. The determinant is a proper subset of "
                                    f"the following candidate keys: {keys}. {right} is non-prime."),
                    })
                determined = closure.of(determinant)
                missing = sorted(attributes - determined)
                third_nf.append({
                    "relation": relation.name, "determinant": left, "dependent": right,
                    "undetermined_attributes": missing,
                    "message": (f"{relation.name}: {_display(left)} -> [{right}] follows from the "
                                f"functional dependencies. The determinant cannot determine "
                                f"{_display(missing)} in this relation, and {right} belongs to "
                                "no candidate key."),
                })
    return second_nf, third_nf


def _project_example_tables(relations, source_rows):
    """Project the witness data to each relation under set semantics."""
    tables = {}
    for relation in relations:
        projected = {tuple(row[column] for column in relation.columns) for row in source_rows}
        tables[relation.name] = [dict(zip(relation.columns, values)) for values in sorted(projected)]
    return tables


def _trace_join(relations, tables, target):
    """Select one example row per table whose natural join yields target."""
    remaining = list(relations)
    joined_columns = set()
    steps = []
    while remaining:
        index = next((i for i, relation in enumerate(remaining)
                      if joined_columns.intersection(relation.columns)), 0)
        relation = remaining.pop(index)
        projected = {column: target[column] for column in relation.columns}
        steps.append({
            "relation": relation.name,
            "row_number": tables[relation.name].index(projected) + 1,
            "join_values": {column: value for column, value in projected.items()
                            if column in joined_columns},
        })
        joined_columns.update(relation.columns)
    return steps


def _display_example_tables(relations, tables):
    lines = ["  Example table rows before the join"]
    for relation in relations:
        lines.append(f"    {relation.name}({', '.join(relation.columns)})")
        for number, row in enumerate(tables[relation.name], start=1):
            values = ", ".join(str(row[column]) for column in relation.columns)
            lines.append(f"      Row {number} ({values})")
    return lines


def _display_assignments(values):
    return ", ".join(f"{attribute}={value}" for attribute, value in values.items())


def _display_join_trace(steps):
    first, *remaining = steps
    lines = [f"    Start with {first['relation']} row {first['row_number']}."]
    for step in remaining:
        row = f"{step['relation']} row {step['row_number']}"
        if step["join_values"]:
            lines.append(f"    Join {row} on {_display_assignments(step['join_values'])}.")
        else:
            lines.append(f"    Combine with {row} by Cartesian product.")
    return lines


def _lossless_join_details(relations, target, witness_rows):
    columns = {relation.name: set(relation.columns) for relation in relations}
    join_attributes = {}
    for attribute in target:
        names = [name for name, attributes in columns.items() if attribute in attributes]
        if len(names) > 1:
            join_attributes[attribute] = names

    spurious_join_pairs = []
    for first, second in combinations(columns, 2):
        shared = columns[first] & columns[second]
        if not shared:
            continue
        combined = columns[first] | columns[second]
        if any(all(row[attribute] == target[attribute] for attribute in combined)
               for row in witness_rows.values()):
            continue
        spurious_join_pairs.append({
            "relations": [first, second],
            "join_values": {attribute: target[attribute] for attribute in sorted(shared)},
        })
    return join_attributes, spurious_join_pairs


def _lossless_violations(relations, dependencies, attributes):
    solver = z3.Solver()
    rows = [{attribute: z3.Int(f"row_{i}_{j}") for j, attribute in enumerate(attributes)}
            for i in range(len(relations))]
    # The proposed spurious tuple uses 0 in each column, by renaming its values.
    for relation, row in zip(relations, rows):
        solver.add(*(row[item] == 0 for item in relation.columns))
        solver.add(z3.Or(*(cell != 0 for cell in row.values())))
    for first, second in combinations(rows, 2):
        for dependency in dependencies:
            agrees_left = z3.And(*(first[item] == second[item]
                                   for item in sorted(dependency.determinant)))
            agrees_right = z3.And(*(first[item] == second[item]
                                    for item in sorted(dependency.dependents)))
            solver.add(z3.Implies(agrees_left, agrees_right))
    if not _satisfiable(solver):
        return []

    model = solver.model()
    spurious = dict.fromkeys(attributes, 0)
    witness_rows = {relation.name: {attribute: model.eval(cell, model_completion=True).as_long()
                                   for attribute, cell in row.items()}
                    for relation, row in zip(relations, rows)}
    example_tables = _project_example_tables(relations, witness_rows.values())
    join_trace = _trace_join(relations, example_tables, spurious)
    join_attributes, spurious_join_pairs = _lossless_join_details(relations, spurious, witness_rows)
    join_lines = []
    for pair in spurious_join_pairs:
        first, second = pair["relations"]
        values = _display_assignments(pair["join_values"])
        join_lines.append(f"  Joining {first} and {second} on {values} produces a spurious combination "
                          "absent from every source row.")
    if not join_attributes:
        join_lines.append("  The relations have disjoint columns, so their natural join is a Cartesian product.")
    elif len(relations) > 2 or not spurious_join_pairs:
        join_lines.extend(f"  Shared join attribute {attribute}={spurious[attribute]} matches across "
                          f"{', '.join(names)}." for attribute, names in join_attributes.items())
    row_lines = [f"    Source row {number}: {values}"
                 for number, values in enumerate(witness_rows.values(), start=1)]
    return [{
        "relations": list(witness_rows), "spurious_tuple": spurious, "witness_rows": witness_rows,
        "join_attributes": join_attributes, "spurious_join_pairs": spurious_join_pairs,
        "example_tables": example_tables, "join_traces": [join_trace],
        "message": "\n".join([
            "Joining the projections can introduce a spurious tuple.",
            *join_lines,
            "  Source data before decomposition (satisfies all supplied dependencies)",
            *row_lines,
            *_display_example_tables(relations, example_tables),
            "  Join trace for the spurious tuple",
            *_display_join_trace(join_trace),
            f"  Spurious tuple: {spurious}",
        ]),
    }]


def _preservation_violations(relations, dependencies, attributes, closure):
    violations = []
    projections = [frozenset(relation.columns) for relation in relations]
    for dependency in dependencies:
        involved = dependency.determinant | dependency.dependents
        if any(involved <= projection for projection in projections):
            continue

        reached = dependency.determinant
        while not dependency.dependents <= reached:
            expanded = reached.union(*(closure.of(reached & projection) & projection
                                       for projection in projections))
            if expanded == reached:
                break
            reached = expanded
        missing = dependency.dependents - reached
        if missing:
            rows = [
                dict.fromkeys(attributes, 0),
                {attribute: int(attribute not in reached) for attribute in attributes},
            ]
            relation_columns = {}
            for relation in relations:
                columns = sorted(involved.intersection(relation.columns))
                if columns:
                    relation_columns[relation.name] = columns
            locations = ", ".join(f"{name}{_display(columns)}"
                                  for name, columns in relation_columns.items())
            example_tables = _project_example_tables(relations, rows)
            join_traces = [_trace_join(relations, example_tables, row) for row in rows]
            witness_lines = []
            for number, (row, trace) in enumerate(zip(rows, join_traces), start=1):
                witness_lines.extend([
                    f"  Join trace for witness row {number}",
                    *_display_join_trace(trace),
                    f"  Joined row {number}: {row}",
                ])
            agreements = {attribute: rows[0][attribute] for attribute in sorted(dependency.determinant)}
            differences = ", ".join(f"{attribute} ({rows[0][attribute]} versus {rows[1][attribute]})"
                                    for attribute in sorted(missing))
            violations.append({
                "dependency": dependency.source,
                "relation_columns": relation_columns,
                "reachable_attributes": sorted(reached),
                "missing_attributes": sorted(missing),
                "witness_rows": rows,
                "example_tables": example_tables,
                "join_traces": join_traces,
                "message": "\n".join([
                    f"{dependency.source} is not preserved. The dependencies enforceable "
                    f"in the individual relations can derive only {_display(reached)} "
                    f"from its determinant. The missing logical attributes are "
                    f"{_display(missing)}. The FD's columns occur in {locations}.",
                    "  Each example table satisfies its projected dependencies.",
                    *_display_example_tables(relations, example_tables),
                    *witness_lines,
                    f"  The joined rows agree on {_display_assignments(agreements)} "
                    f"and differ on {differences}.",
                ]),
            })
    return violations


def verify_schema(
    relational_schema: str,
    functional_dependencies: Sequence[str] | str,
) -> dict:
    """Check 2NF, 3NF, lossless decomposition, and dependency preservation.

    ``relational_schema`` has one ``Relation(A, <u>B</u>)`` declaration per
    line. Column names are case-sensitive and unique within each relation.
    The same name in different relations represents the same logical
    attribute. Use distinct names for different attributes, such as
    ``Student_Name`` and ``Course_Name``. Identifiers contain letters, digits,
    and underscores and start with a letter or underscore. A dotted name
    follows the same rule for each segment. Underline each declared primary
    key column with literal ``<u>`` and ``</u>`` tags. The markers are used in
    feedback. The supplied FDs define implication and candidate keys.

    ``functional_dependencies`` is multiline text or a sequence of strings of
    the form ``[A, B] -> [C, D]`` using the column names from the schema.
    ``[]`` is allowed on the left for a constant attribute. Blank lines are
    ignored in both inputs, and section headings should be omitted. The
    universal relation is assumed to have the union of the named attributes.

    Return a JSON-serializable dictionary. ``verified`` is true when all four
    checks pass. ``checks`` has entries ``2NF``, ``3NF``,
    ``lossless_decomposition``, and ``dependency_preservation``, each with a
    ``passed`` Boolean and a ``violations`` list. Violations include the
    affected relations or attributes, the evidence, and an explanation.
    ``feedback`` combines the explanations by rule or equals ``Verified.``
    when all checks pass. Malformed inputs raise ``ValueError``. An
    inconclusive Z3 result raises ``RuntimeError``.
    """
    relations, attribute_names = parse_relational_schema(relational_schema)
    dependencies = parse_functional_dependencies(functional_dependencies, attribute_names)
    attributes = sorted(attribute_names)
    closure = _Closure(attributes, dependencies)
    second_nf, third_nf = _normal_form_violations(relations, closure)
    violations_by_check = {
        "2NF": second_nf,
        "3NF": third_nf,
        "lossless_decomposition": _lossless_violations(relations, dependencies, attributes),
        "dependency_preservation": _preservation_violations(relations, dependencies, attributes, closure),
    }
    checks = {rule: {"passed": not violations, "violations": violations}
              for rule, violations in violations_by_check.items()}
    verified = all(result["passed"] for result in checks.values())
    feedback = ["Verified." if verified else "Not verified."]
    for rule, violations in violations_by_check.items():
        label = rule.replace("_", " ")
        feedback.extend(f"{label} — {violation['message']}" for violation in violations)
    return {"verified": verified, "checks": checks, "feedback": "\n".join(feedback)}
