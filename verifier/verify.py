"""Verify relational design properties under functional dependencies with Z3."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
import re

import z3


_NAME = re.compile(r"[^\W\d]\w*(?:\.[^\W\d]\w*)*")
_RELATION = re.compile(r"([^()]+)\(([^()]*)\)")
_FD = re.compile(r"\[([^\[\]]*)\]\s*->\s*\[([^\[\]]*)\]")


@dataclass(frozen=True)
class _Relation:
    name: str
    columns: dict[str, str]  # logical attribute -> declared column name
    primary_key: frozenset[str]


@dataclass(frozen=True)
class _Dependency:
    determinant: frozenset[str]
    dependents: frozenset[str]
    source: str


def _name(value: str, location: str) -> str:
    value = value.strip()
    if not _NAME.fullmatch(value):
        raise ValueError(f"{location}: invalid identifier {value!r}.")
    return value


def _parse_inputs(schema_text, dependency_lines, aliases):
    if not isinstance(schema_text, str):
        raise ValueError("Relational schema must be text with one relation per line.")
    if aliases is not None and not isinstance(aliases, Mapping):
        raise ValueError("Attribute aliases must map declared names to logical names.")
    aliases = {} if aliases is None else aliases
    for declared, logical in aliases.items():
        if not all(isinstance(value, str) and _NAME.fullmatch(value)
                   for value in (declared, logical)):
            raise ValueError(f"Invalid attribute alias {declared!r}: {logical!r}.")

    relations = []
    relation_names = set()
    logical_names = {}
    for line_number, line in enumerate(schema_text.splitlines(), start=1):
        if not line.strip():
            continue
        location = f"Schema line {line_number}"
        match = _RELATION.fullmatch(line.strip())
        if match is None:
            raise ValueError(f"{location}: expected Relation(Column, <u>Key</u>).")
        name = _name(match[1], location)
        if name in relation_names:
            raise ValueError(f"{location}: duplicate relation {name!r}.")
        relation_names.add(name)
        columns = {}
        key = set()
        for column in match[2].split(","):
            column = column.strip()
            is_key = column.startswith("<u>") and column.endswith("</u>")
            declared = _name(column[3:-4] if is_key else column, location)
            if declared in logical_names:
                raise ValueError(f"{location}: column {declared!r} must be globally unique.")
            logical = aliases.get(declared, declared)
            if logical in columns:
                raise ValueError(f"{location}: two columns map to logical attribute {logical!r}.")
            columns[logical] = declared
            logical_names[declared] = logical
            if is_key:
                key.add(logical)
        relations.append(_Relation(name, columns, frozenset(key)))
    if not relations:
        raise ValueError("Relational schema must contain at least one relation.")
    unknown_aliases = aliases.keys() - logical_names.keys()
    if unknown_aliases:
        raise ValueError(f"Aliases reference undeclared columns {_display(unknown_aliases)}.")

    if isinstance(dependency_lines, str):
        dependency_lines = dependency_lines.splitlines()
    if not isinstance(dependency_lines, Sequence):
        raise ValueError("Functional dependencies must be text or a sequence of strings.")

    attributes = sorted(set(logical_names.values()))
    references = {**{item: item for item in attributes}, **logical_names}
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
            left = [_name(item, location) for item in match[1].split(",")]
        right = [_name(item, location) for item in match[2].split(",")]
        unknown = set(left + right) - references.keys()
        if unknown:
            raise ValueError(f"{location}: unknown attributes {_display(unknown)} in {line!r}.")
        dependencies.append(_Dependency(
            frozenset(references[item] for item in left),
            frozenset(references[item] for item in right),
            line,
        ))
    return relations, dependencies, attributes


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
                left = sorted(relation.columns[item] for item in determinant)
                right = relation.columns[dependent]
                partial = [
                    (sorted(relation.columns[item] for item in key), key == relation.primary_key)
                    for key in candidate_keys if determinant < key
                ]
                if partial:
                    keys = ", ".join(_display(key) + (" (declared primary key)" if marked else "")
                                     for key, marked in partial)
                    second_nf.append({
                        "relation": relation.name, "determinant": left, "dependent": right,
                        "candidate_keys": [key for key, _ in partial],
                        "message": (f"{relation.name}: {_display(left)} -> [{right}] is a partial "
                                    f"dependency. The determinant is a proper subset of "
                                    f"the following candidate keys: {keys}. {right} is non-prime."),
                    })
                determined = closure.of(determinant)
                missing = sorted(relation.columns[item] for item in attributes - determined)
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
                columns = sorted(declared for logical, declared in relation.columns.items()
                                 if logical in involved)
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
    *,
    attribute_aliases: Mapping[str, str] | None = None,
) -> dict:
    """Check 2NF, 3NF, lossless decomposition, and dependency preservation.

    ``relational_schema`` has one ``Relation(A, <u>B</u>)`` declaration per
    line. Use globally unique, case-sensitive column names. Identifiers are
    letters, digits and underscores, starting with a letter or underscore.
    Dot-qualified names follow the same rule for each segment. Underline all
    columns of a declared primary key with literal ``<u>`` and ``</u>`` tags.
    The markers are used in feedback. The supplied FDs define all implication
    and candidate-key calculations.

    ``functional_dependencies`` is multiline text or a sequence of strings of
    the form ``[A, B] -> [C, D]`` using exact declared column names or logical
    identifiers. A declared name takes precedence if both match. ``[]`` is
    allowed on the left for a constant attribute. Blank lines are ignored in
    both inputs, and section headings should be omitted.

    ``attribute_aliases`` optionally maps declared column names to logical
    identifiers. Map columns in different relations to the same identifier
    when they stand for the same universal-relation attribute. An unmapped
    column is its own logical identifier. The universal relation is assumed
    to have the union of these logical attributes.

    Return a JSON-serializable dictionary. ``verified`` is true when all four
    checks pass. ``checks`` has entries ``2NF``, ``3NF``,
    ``lossless_decomposition``, and ``dependency_preservation``, each with a
    ``passed`` Boolean and a ``violations`` list. Violations include the
    affected relations or attributes, the evidence, and an explanation.
    ``feedback`` combines the explanations by rule or equals ``Verified.``
    when all checks pass. Malformed inputs raise ``ValueError``. An
    inconclusive Z3 result raises ``RuntimeError``.
    """
    relations, dependencies, attributes = _parse_inputs(
        relational_schema, functional_dependencies, attribute_aliases,
    )
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
