export const SHIFT_NAME = { morning: 'Morning', night: 'Night' }
export const FIXED_ROLES = ['Driver', 'Toilet', 'Truck']
// Driver and Truck are both trackable licences (shown/toggled wherever qualifications are listed).
export const QUAL_ROLES = ['Driver', 'Truck']
export const QUAL_LABEL = { Driver: 'Airport driver licence', Truck: 'Truck driver licence' }
// Of the fixed roles, only Driver actually requires holding the matching licence to be picked for
// today -- Truck duty also covers just helping load/unload, which anyone on duty can do. Toilet
// needs neither.
export const LICENCE_REQUIRED_ROLES = ['Driver']
// Positions offered as quick-add chips on an aircraft, by kind of flight -- the same lists as the
// backend's default layouts (services/domain.py), so a removed default position can be put back.
export const PRESET_ROLES = {
  international: [
    'Leading Hand',
    'Toilet',
    'Business',
    'Vacuum',
    'Economy - Front Y1',
    'Economy - Front Y2',
    'Economy - Front Y3',
    'Economy - Back Y1',
    'Economy - Back Y2',
    'Economy - Back Y3',
    'Galley',
  ],
  domestic: ['Leading Hand', 'Toilet', 'Business', 'Vacuum', 'Galley', 'Seats'],
}
export const STATUS_LABEL = {
  sched: 'Scheduled',
  landed: 'Landed',
  cleaning: 'Cleaning',
  done: 'Done',
  cancelled: 'Cancelled',
}
export const THEME_COLOR = { morning: '#F5B544', night: '#1A2750' }
