// Names come in as "Full Name - 08316" from the import; drop the trailing employee number where
// space is tight and the number isn't needed to tell people apart.
export const shortName = (name) => name.replace(/\s-\s*\d+$/, '')
