export const SHIFT_LABEL = { early: 'Early', late: 'Late', all: 'All day' }
export const SHIFT_ORDER = { early: 0, late: 1, all: 2 }
// Standard Start/Indicative End for each shift type, calibrated from the real roster (matches the
// thresholds in the backend's derive_shift_type). Switching someone's type jumps their times to
// these -- still editable afterwards for a genuinely one-off time.
export const SHIFT_TIMES = { early: ['15:50', '22:15'], late: ['19:50', '23:55'], all: ['15:50', '23:55'] }
export const SHIFT_NAME = { morning: 'Morning', night: 'Night' }
export const FIXED_ROLES = ['Driver', 'Toilet', 'Truck']
// Driver and Truck are both trackable licences (shown/toggled wherever qualifications are listed).
export const QUAL_ROLES = ['Driver', 'Truck']
export const QUAL_LABEL = { Driver: 'Airport driver licence', Truck: 'Truck driver licence' }
// Of the fixed roles, only Driver actually requires holding the matching licence to be picked for
// today -- Truck duty also covers just helping load/unload, which anyone on duty can do. Toilet
// needs neither.
export const LICENCE_REQUIRED_ROLES = ['Driver']
export const PRESET_ROLES = ['Business', 'Vacuum', 'Economy - Front', 'Economy - Mid', 'Economy - Rear', 'Toilet', 'Leading Hand']
export const STATUS_LABEL = {
  sched: 'Scheduled',
  landed: 'Landed',
  cleaning: 'Cleaning',
  done: 'Done',
  cancelled: 'Cancelled',
}
export const THEME_COLOR = { morning: '#F5B544', night: '#1A2750' }
