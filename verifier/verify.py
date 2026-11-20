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
    row_lines = [f"  Row for {name}: {values}" for name, values in witness_rows.items()]
    return [{
        "relations": list(witness_rows), "spurious_tuple": spurious, "witness_rows": witness_rows,
        "message": ("Joining the projections can introduce a spurious tuple. The rows below "
                    "satisfy all supplied dependencies, and each named relation's projection "
                    "has a matching row for the tuple. None of the source rows is that tuple.\n"
                    f"  Spurious tuple: {spurious}\n" + "\n".join(row_lines)),
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
            violations.append({
                "dependency": dependency.source,
                "relation_columns": relation_columns,
                "reachable_attributes": sorted(reached),
                "missing_attributes": sorted(missing),
                "witness_rows": rows,
                "message": (f"{dependency.source} is not preserved. The dependencies enforceable "
                            f"in the individual relations can derive only {_display(reached)} "
                            f"from its determinant. The missing logical attributes are "
                            f"{_display(missing)}. The FD's columns occur in {locations}. "
                            "These two rows satisfy every projected "
                            f"dependency and violate the supplied dependency: {rows}"),
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
