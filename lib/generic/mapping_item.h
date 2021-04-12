struct ITEM_STRUCT {
	uint32_t hash;   // 0 if entry is unused
	KEY memb_key;
	VALUE memb_value;
};

void ITEM_INCREF(ITEM it);
void ITEM_DECREF(ITEM it);
