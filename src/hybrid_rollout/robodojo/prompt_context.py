"""
Version of teacher-visible evaluation guidance, independent of model/source.

Thanks for the contribution: https://github.com/anonymous-report-421/GPT-as-Policy

"""

CONTEXT_VERSION = 'v4_category_ledger'

CATEGORY_COMPLETION_POLICY = {
    'ledger_fields': ['category', 'destination', 'instances', 'verified_complete'],
    'priority': (
        'Maintain an instance ledger. Finish and verify every visible instance in one '
        'category before switching when feasible; only mark category_complete after all '
        'instances are visibly in the correct destination, settled, and the grippers '
        'are clear. If the horizon is short, continue the category nearest to completion '
        'instead of spreading small corrections across all categories.'
    ),
    'evidence': (
        'A grab, lift, or closed gripper command is not completion. Verify post-release '
        'object motion and containment from a fresh observation; revoke completion if '
        'a later observation shows a slip or wrong destination.'
    ),
}

# Public task semantics only: no layout truth, score queries or action script.
TASK_NOTES = {
    'organize_table': 'Place the named desk items at their instructed destinations, then put the remaining items inside the drawer.',
    'classify_objects_by_language': 'Follow this episode\'s language-specified category-to-basket mapping for every object.',
    'imitate_sorting_sequence': 'Observe and remember the demonstration before placing the corresponding objects in the same order.',
    'arrange_largest_number': 'Arrange the digits left to right as the largest number, correctly oriented and placed on their pads.',
    'pack_objects_into_box': 'Place every object inside the box with its front facing left, as instructed.',
    'classify_objects': 'Group all objects by category into the three baskets.',
    'build_tower': 'Build the supported tower layers using the wooden blocks and boards.',
    'make_kong': 'Wait for the discard, expose the matching tiles, and finish the tile-handling sequence without disturbing the other tiles.',
    'fold_clothes': 'Fold the sleeves inward and the lower garment upward into a neat folded shape.',
    'put_bottles_into_dustbin': 'Put all bottles inside the dustbin.',
}


def task_context(task):
    base = task.removesuffix('_random')
    if base not in TASK_NOTES:
        return {}
    result = dict(process=TASK_NOTES[base], requires_arm_return=base != 'make_kong')
    if base in {'classify_objects_by_language', 'classify_objects'}:
        result['category_completion'] = CATEGORY_COMPLETION_POLICY
    return result
