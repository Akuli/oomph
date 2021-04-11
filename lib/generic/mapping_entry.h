struct ENTRY_STRUCT {
	uint32_t hash;   // 0 if entry is unused
	KEY memb_key;
	VALUE memb_value;
};

void ENTRY_INCREF(ENTRY e);
void ENTRY_DECREF(ENTRY e);
