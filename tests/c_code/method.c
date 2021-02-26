struct class_Point {
	REFCOUNT_HEADER
	int64_t memb_x;
	int64_t memb_y;
	
};
struct class_Point *ctor_Point(int64_t var_x,int64_t var_y) {
	struct class_Point *obj = malloc(sizeof(*obj));
	obj->refcount = 1;
	obj->memb_x = var_x;
	obj->memb_y = var_y;
	return obj;
}
void meth_Point_print(struct class_Point *var_self){
	(var_print_int(((var_self)->memb_x)));
	(var_print_int(((var_self)->memb_y)));
	out:
	(void)0;
}
struct class_Point *meth_Point_add(struct class_Point *var_self,struct class_Point *var_other){
	void *retval = NULL;
	void *ref0 = NULL;
	retval = (ref0 = (ctor_Point((var_add(((var_self)->memb_x),((var_other)->memb_x))),(var_add(((var_self)->memb_y),((var_other)->memb_y))))));incref(retval);goto out;
	out:
	if (ref0) decref(ref0);
	(void)0;assert(retval); return retval;
	
}
void var_main(void){
	void *ref1 = NULL;
	void *ref2 = NULL;
	void *ref3 = NULL;
	void *ref4 = NULL;
	(meth_Point_print((ref1 = (ctor_Point(((int64_t)100LL),((int64_t)200LL))))));
	struct class_Point *var_p = (ref2 = (ctor_Point(((int64_t)100LL),((int64_t)200LL))));
	(meth_Point_print((ref4 = (meth_Point_add(var_p,(ref3 = (ctor_Point(((int64_t)1LL),((int64_t)2LL)))))))));
	out:
	if (ref4) decref(ref4);
	if (ref3) decref(ref3);
	if (ref2) decref(ref2);
	if (ref1) decref(ref1);
	(void)0;
}
