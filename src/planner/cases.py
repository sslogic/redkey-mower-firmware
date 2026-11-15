"""Synthetic maps in meters; these are not a reconstruction of a real lawn."""
CASES = {
 'rectangle': {'boundary':[(0,0),(10,0),(10,8),(0,8)],'clearance_m':0.25},
 'u_shape': {'boundary':[(0,0),(4,0),(4,6),(8,6),(8,0),(12,0),(12,10),(0,10)],'clearance_m':0.25},
 'two_squares_passage': {'boundary':[(0,0),(6,0),(6,2.5),(10,2.5),(10,0),(16,0),(16,7),(10,7),(10,4.5),(6,4.5),(6,7),(0,7)],'clearance_m':0.25},
 'obstacle': {'boundary':[(0,0),(10,0),(10,8),(0,8)],'holes':[[(4,3),(6,3),(6,5),(4,5)]],'clearance_m':0.25},
 'sloping_edges': {'boundary':[(0,0),(9,0),(11,5),(7,9),(1,7)],'clearance_m':0.25},
 'l_shape': {'boundary':[(0,0),(9,0),(9,3),(4,3),(4,9),(0,9)],'clearance_m':0.25}
}
