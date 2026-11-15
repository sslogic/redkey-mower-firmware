import copy
import math
import unittest
from shapely.geometry import Polygon, LineString
from planner import (build_plan, load_rules, frame_point, partition_regions,
                     PlanningError, SafetyState, blade_allowed)
from cases import CASES


class PlannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plans={name:build_plan(**case) for name,case in CASES.items()}

    def test_one_mapping_then_two_ordered_sweeps(self):
        for plan in self.plans.values():
            actions=plan['actions']
            self.assertEqual([a['kind'] for a in actions].count('MAP_ONCE'),1)
            self.assertEqual(actions[0]['circuits'],1)
            phases=[a['phase'] for a in actions[1:]]
            split=phases.index('vertical')
            self.assertTrue(all(x=='horizontal' for x in phases[:split]))
            self.assertTrue(all(x=='vertical' for x in phases[split:]))

    def test_routes_stay_inside_clearance_space_and_are_continuous(self):
        for name,plan in self.plans.items():
            case=CASES[name]
            space=Polygon(case['boundary'],case.get('holes',())).buffer(-case['clearance_m'],join_style=2)
            previous=None
            for action in plan['actions'][1:]:
                self.assertTrue(space.buffer(1e-7).covers(LineString(action['points'])),(name,action))
                if previous is not None:
                    self.assertLess(math.dist(previous,action['points'][0]),1e-6)
                previous=action['points'][-1]

    def test_parallel_cuts_diagonal_returns_no_lane_skipping(self):
        for plan in self.plans.values():
            groups={}
            for a in plan['actions'][1:]:
                if a['kind']=='TRANSFER':
                    continue
                local=[frame_point(p,a['phase']) for p in a['points']]
                if a['kind']=='PARALLEL_CUT':
                    self.assertGreater(local[0][0],local[1][0])
                    self.assertAlmostEqual(local[0][1],local[1][1])
                else:
                    self.assertEqual(a['kind'],'DIAGONAL_CUT')
                    self.assertGreater(local[0][1],local[1][1])
                groups.setdefault((a['phase'],a['section']),[]).append(a)
            for actions in groups.values():
                expected=['PARALLEL_CUT' if i%2==0 else 'DIAGONAL_CUT' for i in range(len(actions))]
                self.assertEqual([a['kind'] for a in actions],expected)
                self.assertEqual([a['row'] for a in actions if a['kind']=='PARALLEL_CUT'],list(range((len(actions)+1)//2)))

    def test_each_section_completed_once_per_phase(self):
        for plan in self.plans.values():
            for phase in ('horizontal','vertical'):
                order=[]
                for a in plan['actions'][1:]:
                    if a['phase']==phase and a['kind']=='PARALLEL_CUT' and (not order or order[-1]!=a['section']):
                        order.append(a['section'])
                self.assertEqual(len(order),len(set(order)))
                self.assertEqual(len(order),plan['metrics'][phase]['sections'])

    def test_passage_and_u_shape_are_separate_sections(self):
        for name in ('u_shape','two_squares_passage'):
            for phase in ('horizontal','vertical'):
                self.assertEqual(self.plans[name]['metrics'][phase]['sections'],3)
            # Parallel cuts must not repeatedly run all the way across both squares.
        horizontal=[a for a in self.plans['two_squares_passage']['actions']
                    if a.get('phase')=='horizontal' and a['kind']=='PARALLEL_CUT']
        self.assertLess(max(a['length_m'] for a in horizontal),7)

    def test_coverage_is_measured_and_center_space_has_no_material_gaps(self):
        for name,plan in self.plans.items():
            for phase,m in plan['metrics'].items():
                self.assertLess(m['uncovered_center_space_m2'],0.005,(name,phase,m))
                self.assertGreater(m['uncut_boundary_margin_m2'],0)

    def test_blade_request_and_every_protective_stop(self):
        for plan in self.plans.values():
            self.assertTrue(all(a['blade_request'] is True for a in plan['actions'][1:]))
        self.assertFalse(blade_allowed(True,SafetyState()))
        self.assertTrue(blade_allowed(True,SafetyState(status_known=True)))
        for field in ('lifted','tilted','emergency_stop','fault','operator_stop'):
            self.assertFalse(blade_allowed(True,SafetyState(status_known=True,**{field:True})))
        self.assertFalse(blade_allowed(False,SafetyState(status_known=True)))

    def test_invalid_and_disconnected_maps_rejected(self):
        with self.assertRaises(PlanningError):
            build_plan([(0,0),(4,4),(0,4),(4,0)],clearance_m=.25)
        with self.assertRaises(PlanningError):
            build_plan(CASES['rectangle']['boundary'],clearance_m=.01)
        # A neck which is narrower than the configured robot clearance.
        narrow=[(0,0),(4,0),(4,1.9),(8,1.9),(8,0),(12,0),(12,4),(8,4),(8,2.1),(4,2.1),(4,4),(0,4)]
        with self.assertRaisesRegex(PlanningError,'disconnects'):
            build_plan(narrow,clearance_m=.25)

    def test_supplied_rules_cannot_bypass_contract(self):
        for key,value in [('mapping_circuits_per_job',2),
                          ('nominal_overlap_m',float('nan')),
                          ('boundary_follow_between_rows',True)]:
            rules=load_rules()
            rules[key]=value
            with self.assertRaises(PlanningError):
                build_plan(**CASES['rectangle'],rules=rules)

    def test_return_to_dock_does_not_remap(self):
        plan=build_plan(**CASES['u_shape'],dock=(11.5,5))
        self.assertEqual(plan['actions'][-1]['kind'],'RETURN_TO_DOCK')
        self.assertEqual(plan['actions'][-1]['points'][-1],(11.5,5))
        self.assertFalse(plan['actions'][-1]['blade_request'])


if __name__=='__main__':
    unittest.main(verbosity=2)
